#!/usr/bin/env python3
"""
Test the new matching quiz functionality
"""

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import json
import random

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Mock word data
mock_words = [
    {"id": 1, "term": "ubiquitous", "definition": "Present, appearing, or found everywhere", "part_of_speech": "ADJECTIVE"},
    {"id": 2, "term": "serendipity", "definition": "The occurrence and development of events by chance in a happy or beneficial way", "part_of_speech": "NOUN"},  
    {"id": 3, "term": "ephemeral", "definition": "Lasting for a very short time", "part_of_speech": "ADJECTIVE"},
    {"id": 4, "term": "mellifluous", "definition": "Sweet or musical; pleasant to hear", "part_of_speech": "ADJECTIVE"},
    {"id": 5, "term": "perspicacious", "definition": "Having a ready insight into and understanding of things", "part_of_speech": "ADJECTIVE"},
    {"id": 6, "term": "obfuscate", "definition": "Render obscure, unclear, or unintelligible", "part_of_speech": "VERB"}
]

@app.get("/test-matching", response_class=HTMLResponse)
async def test_matching_quiz(request: Request):
    """Create a test matching quiz"""
    
    # Create a matching question with 4 words
    quiz_words = random.sample(mock_words, 4)
    
    # Create lists of terms and definitions  
    terms = [w["term"] for w in quiz_words]
    definitions = [w["definition"] for w in quiz_words]
    
    # Shuffle definitions but keep track of correct matches
    shuffled_definitions = definitions.copy()
    random.shuffle(shuffled_definitions)
    
    # Create correct answer mapping
    correct_matches = {}
    for i, word in enumerate(quiz_words):
        correct_def_index = shuffled_definitions.index(word["definition"])
        correct_matches[i] = correct_def_index
    
    # Create question data
    question_data = {
        "id": 1,
        "word_id": quiz_words[0]["id"],
        "question_type": "matching",
        "question": "Match each word with its correct definition:",
        "explanation": f"Correct matches: {', '.join([f'{quiz_words[i]['term']} = {quiz_words[i]['definition']}' for i in range(len(quiz_words))])}",
        "terms": terms,
        "definitions": shuffled_definitions,
        "correct_matches": correct_matches
    }
    
    questions = [question_data]
    
    return templates.TemplateResponse("quiz_session.html", {
        "request": request,
        "current_user": None,
        "questions": questions,
        "quiz_type": "matching",
        "difficulty": "medium",
        "session_id": f"test_session_{random.randint(1000, 9999)}"
    })

@app.post("/quiz/submit", response_class=HTMLResponse) 
async def submit_quiz(request: Request,
                     session_id: str = Form(...),
                     results: str = Form(...)):
    """Handle quiz submission"""
    
    try:
        results_data = json.loads(results)
        
        total_questions = results_data.get('totalQuestions', 0)
        correct_count = results_data.get('correctCount', 0)
        score = results_data.get('score', 0)
        difficulty = results_data.get('difficulty', 'medium')
        quiz_type = results_data.get('quizType', 'matching')
        question_results = results_data.get('questions', [])
        
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
        return f"<h1>✅ Matching Quiz Test Successful!</h1><p>Session: {session_id}</p><p>Results received and parsed successfully!</p><p>Raw data: {results}</p>"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)