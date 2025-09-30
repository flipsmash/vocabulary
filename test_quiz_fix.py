#!/usr/bin/env python3
"""
Minimal test to verify quiz submit endpoint fix
"""

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
import json

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/test", response_class=HTMLResponse)
async def test_form():
    """Serve test form"""
    return FileResponse("test_quiz_submit.html")

@app.post("/quiz/submit", response_class=HTMLResponse)
async def submit_quiz(request: Request,
                     session_id: str = Form(...),
                     results: str = Form(...)):
    """Handle quiz submission and show results"""
    
    try:
        # Parse the results JSON
        results_data = json.loads(results)
        
        # Extract quiz information
        total_questions = results_data.get('totalQuestions', 0)
        correct_count = results_data.get('correctCount', 0)
        score = results_data.get('score', 0)
        difficulty = results_data.get('difficulty', 'medium')
        quiz_type = results_data.get('quizType', 'mixed')
        question_results = results_data.get('questions', [])
        
        # Calculate accuracy percentage
        accuracy = round((correct_count / total_questions * 100) if total_questions > 0 else 0, 1)
        
        return templates.TemplateResponse("quiz_results.html", {
            "request": request,
            "current_user": None,
            "session_id": session_id,
            "total_questions": total_questions,
            "correct_count": correct_count,
            "accuracy": accuracy,
            "score": score,
            "difficulty": difficulty,
            "quiz_type": quiz_type,
            "question_results": question_results
        })
        
    except Exception as e:
        return f"<h1>Quiz Results Processed Successfully!</h1><p>Session: {session_id}</p><p>Raw Results: {results}</p><p>Error: {str(e)}</p>"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)