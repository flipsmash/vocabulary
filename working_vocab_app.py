#!/usr/bin/env python3
"""
Working Vocabulary Web App - Minimal version that actually works
"""

from fastapi import FastAPI, Request, Query, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import random
import pymysql
from config import VocabularyConfig
import bcrypt
import secrets
from datetime import datetime, timedelta
import jwt

app = FastAPI(title="Working Vocabulary App")
templates = Jinja2Templates(directory="templates")

# Authentication configuration
SECRET_KEY = "your-secret-key-here-change-in-production"  # In production, use environment variable
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Sessions store (in production, use Redis or database)
active_sessions = {}

class User:
    def __init__(self, user_id: int, username: str, email: str, role: str = "user"):
        self.id = user_id
        self.username = username
        self.email = email
        self.role = role

# Database connection
def get_db_connection():
    """Create database connection"""
    try:
        connection = pymysql.connect(
            host=VocabularyConfig.DATABASE['host'],
            port=VocabularyConfig.DATABASE['port'],
            user=VocabularyConfig.DATABASE['user'],
            password=VocabularyConfig.DATABASE['password'],
            database=VocabularyConfig.DATABASE['database'],
            connect_timeout=10,
            read_timeout=10,
            write_timeout=10
        )
        return connection
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

def get_random_words(num_words=10, domain=None, part_of_speech=None):
    """Get random words from database with optional filters"""
    connection = get_db_connection()
    if not connection:
        return SAMPLE_WORDS[:num_words]  # Fallback to sample data
    
    try:
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        
        # Build query with optional filters using the actual 'defined' table
        query = """
        SELECT id, term, definition, part_of_speech
        FROM defined 
        WHERE 1=1
        """
        params = []
        
        # Domain filtering not available in current schema
            
        if part_of_speech and part_of_speech != "All Parts of Speech":
            query += " AND part_of_speech = %s"
            params.append(part_of_speech)
            
        query += " ORDER BY RAND() LIMIT %s"
        params.append(num_words * 3)  # Get more than needed for variety
        
        cursor.execute(query, params)
        words = cursor.fetchall()
        
        # Randomly select from the results
        if len(words) > num_words:
            words = random.sample(words, num_words)
            
        return words
        
    except Exception as e:
        print(f"Database query failed: {e}")
        raise Exception(f"Failed to get words from database: {e}")
    finally:
        connection.close()

def get_distractor_words(target_word_id, num_distractors=3):
    """Get distractor words for quiz questions"""
    connection = get_db_connection()
    if not connection:
        raise Exception("Database connection failed - quiz requires database access")
    
    try:
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        
        # Get words with same part of speech from defined table
        query = """
        SELECT d.id, d.term, d.definition, d.part_of_speech
        FROM defined d
        WHERE d.id != %s
        AND d.part_of_speech = (
            SELECT part_of_speech FROM defined WHERE id = %s
        )
        ORDER BY RAND()
        LIMIT %s
        """
        
        cursor.execute(query, [target_word_id, target_word_id, num_distractors * 2])
        distractors = cursor.fetchall()
        
        # Randomly select from results
        if len(distractors) > num_distractors:
            distractors = random.sample(distractors, num_distractors)
            
        return distractors
        
    except Exception as e:
        print(f"Distractor query failed: {e}")
        raise Exception(f"Failed to get distractor words: {e}")
    finally:
        connection.close()

# Authentication functions
def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_user(username: str, email: str, password: str) -> Optional[int]:
    """Create a new user in the database"""
    connection = get_db_connection()
    if not connection:
        return None
    
    try:
        cursor = connection.cursor()
        
        # Check if user already exists
        cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
        if cursor.fetchone():
            return None  # User already exists
        
        # Create new user
        hashed_password = hash_password(password)
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, role, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (username, email, hashed_password, 'user'))
        
        connection.commit()
        return cursor.lastrowid
        
    except Exception as e:
        print(f"Error creating user: {e}")
        connection.rollback()
        return None
    finally:
        connection.close()

def authenticate_user(username: str, password: str) -> Optional[User]:
    """Authenticate user credentials"""
    connection = get_db_connection()
    if not connection:
        return None
    
    try:
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        cursor.execute("""
            SELECT id, username, email, password_hash, role
            FROM users WHERE username = %s
        """, (username,))
        
        user_data = cursor.fetchone()
        if not user_data:
            return None
        
        if verify_password(password, user_data['password_hash']):
            return User(
                user_id=user_data['id'],
                username=user_data['username'],
                email=user_data['email'],
                role=user_data['role']
            )
        return None
        
    except Exception as e:
        print(f"Error authenticating user: {e}")
        return None
    finally:
        connection.close()

def get_current_user(request: Request) -> Optional[User]:
    """Get current user from session"""
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in active_sessions:
        return None
    
    session_data = active_sessions[session_id]
    
    # Check if session is expired
    if datetime.utcnow() > session_data['expires']:
        del active_sessions[session_id]
        return None
    
    return session_data['user']

def create_session(user: User) -> str:
    """Create a new session for user"""
    session_id = secrets.token_urlsafe(32)
    active_sessions[session_id] = {
        'user': user,
        'expires': datetime.utcnow() + timedelta(hours=24),
        'created': datetime.utcnow()
    }
    return session_id

# Sample vocabulary data for testing (ONLY FOR FALLBACK - MUST USE DATABASE)
SAMPLE_WORDS = [
    {
        "id": 1,
        "term": "abacinate",
        "definition": "To blind by placing red-hot irons or reflective metal plates in front of the eyes",
        "part_of_speech": "VERB",
        "domain": "Historical"
    },
    {
        "id": 2,
        "term": "abdicate",
        "definition": "To give up power or responsibility",
        "part_of_speech": "VERB",
        "domain": "Political"
    },
    {
        "id": 3,
        "term": "aberrant",
        "definition": "Departing from an accepted standard",
        "part_of_speech": "ADJECTIVE",
        "domain": "Academic"
    },
    {
        "id": 4,
        "term": "abeyance",
        "definition": "A state of temporary disuse or suspension",
        "part_of_speech": "NOUN",
        "domain": "Legal"
    },
    {
        "id": 5,
        "term": "abscond",
        "definition": "Leave hurriedly and secretly, typically to avoid detection or arrest",
        "part_of_speech": "VERB",
        "domain": "Legal"
    }
]

# PROJECT NOTE: NO SAMPLE DATA WORKAROUNDS! 
# Database connection MUST work or the feature does NOT work.
# Sample data is only for emergency fallback, never for permanent solutions.

DOMAINS = ["Academic", "Historical", "Political", "Legal", "Scientific", "Medical"]
PARTS_OF_SPEECH = ["NOUN", "VERB", "ADJECTIVE", "ADVERB"]

@app.get("/test")
async def test():
    """Test endpoint"""
    return {"status": "working", "message": "Vocabulary app is running!"}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page with search interface"""
    current_user = get_current_user(request)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "current_user": current_user,
        "words": SAMPLE_WORDS[:3],  # Show some sample words
        "query": "",
        "domains": DOMAINS,
        "parts_of_speech": PARTS_OF_SPEECH
    })

@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Query("")):
    """Search for words"""
    # Simple search in sample data
    if q:
        results = [word for word in SAMPLE_WORDS if q.lower() in word["term"].lower() or q.lower() in word["definition"].lower()]
    else:
        results = SAMPLE_WORDS
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "current_user": None,
        "words": results,
        "query": q,
        "domains": DOMAINS,
        "parts_of_speech": PARTS_OF_SPEECH
    })

@app.get("/quiz", response_class=HTMLResponse)
async def quiz_home(request: Request):
    """Quiz home page"""
    return templates.TemplateResponse("quiz.html", {
        "request": request,
        "current_user": None,
        "domains": DOMAINS,
        "parts_of_speech": PARTS_OF_SPEECH
    })

@app.post("/quiz/start", response_class=HTMLResponse)
async def start_quiz(request: Request,
                    difficulty: str = Form("medium"),
                    quiz_type: str = Form("mixed"),
                    domain: Optional[str] = Form(None),
                    part_of_speech: Optional[str] = Form(None),
                    num_questions: int = Form(5)):
    """Start a working quiz"""
    # Get random words from database with filters
    quiz_words = get_random_words(num_questions, domain, part_of_speech)
    questions = []
    
    for i, word in enumerate(quiz_words):
        question_id = i + 1
        
        # Determine question type for this question
        if quiz_type == "mixed":
            actual_type = random.choice(["multiple_choice", "true_false"])
        elif quiz_type == "multiple_choice":
            actual_type = "multiple_choice" 
        elif quiz_type == "true_false":
            actual_type = "true_false"
        else:
            actual_type = "multiple_choice"  # fallback
        
        if actual_type == "true_false":
            # Create True/False question
            # 50% chance of correct definition, 50% chance of wrong definition
            if random.choice([True, False]):
                # Use correct definition
                question_text = f"True or False: '{word['term']}' means '{word['definition']}'"
                correct_answer = True
                explanation = f"TRUE: '{word['term']}' does mean '{word['definition']}'"
            else:
                # Use wrong definition from another word
                distractors = get_distractor_words(word["id"], 1)
                if distractors:
                    wrong_word = distractors[0]
                    question_text = f"True or False: '{word['term']}' means '{wrong_word['definition']}'"
                    correct_answer = False
                    explanation = f"FALSE: '{word['term']}' actually means '{word['definition']}', not '{wrong_word['definition']}'"
                else:
                    # Fallback to multiple choice if no distractors
                    actual_type = "multiple_choice"
        
        if actual_type == "multiple_choice":
            # Create multiple choice question
            distractors = get_distractor_words(word["id"], 3)
            distractor_definitions = [d["definition"] for d in distractors]
            
            options = [word["definition"]] + distractor_definitions
            random.shuffle(options)
            correct_answer = options.index(word["definition"])
            question_text = f"What is the definition of '{word['term']}'?"
            explanation = f"'{word['term']}' means: {word['definition']}"
        
        # Add question to list
        question_data = {
            "id": question_id,
            "word_id": word["id"],
            "question_type": actual_type,
            "question": question_text,
            "explanation": explanation
        }
        
        if actual_type == "multiple_choice":
            question_data["options"] = options
            question_data["correct_answer"] = correct_answer
        else:  # true_false
            question_data["correct_answer"] = correct_answer
            
        questions.append(question_data)
    
    return templates.TemplateResponse("quiz_session.html", {
        "request": request,
        "current_user": None,
        "questions": questions,
        "quiz_type": quiz_type,
        "difficulty": difficulty,
        "session_id": "test_session"
    })

@app.post("/quiz/submit", response_class=HTMLResponse)
async def submit_quiz(request: Request,
                     session_id: str = Form(...),
                     results: str = Form(...)):
    """Handle quiz submission and show results summary"""
    import json
    
    try:
        # Parse the results JSON
        results_data = json.loads(results)
        
        # Extract quiz performance data
        correct_count = results_data.get('correct_count', 0)
        total_questions = results_data.get('total_questions', 0)
        accuracy = results_data.get('accuracy', 0)
        difficulty = results_data.get('difficulty', 'Unknown')
        question_results = results_data.get('question_results', [])
        
        # Process individual question results
        correct_words = []
        incorrect_words = []
        
        for question_result in question_results:
            word_id = question_result.get('word_id')
            is_correct = question_result.get('is_correct', False)
            question_type = question_result.get('question_type', 'unknown')
            
            # Get word details (from database in real implementation)
            word_data = get_word_by_id(word_id)
            
            if word_data:
                word_info = {
                    'term': word_data.get('term', 'Unknown'),
                    'definition': word_data.get('definition', 'No definition available'),
                    'part_of_speech': word_data.get('part_of_speech', ''),
                    'domain': word_data.get('domain', ''),
                    'question_type': question_type
                }
                
                if is_correct:
                    correct_words.append(word_info)
                else:
                    incorrect_words.append(word_info)
        
        # Log the results
        print(f"Quiz completed - Session: {session_id}, Accuracy: {accuracy}%")
        
        return templates.TemplateResponse("quiz_results.html", {
            "request": request,
            "current_user": None,
            "session_id": session_id,
            "correct_count": correct_count,
            "total_questions": total_questions,
            "accuracy": accuracy,
            "difficulty": difficulty,
            "correct_words": correct_words,
            "incorrect_words": incorrect_words
        })
        
    except json.JSONDecodeError:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Invalid quiz results format"
        })
    except Exception as e:
        print(f"Error processing quiz results: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Failed to process quiz results"
        })

def get_word_by_id(word_id):
    """Get word details by ID (database lookup)"""
    connection = get_db_connection()
    if not connection:
        raise Exception("Database connection failed")
    
    try:
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        cursor.execute("""
            SELECT id, term, definition, part_of_speech
            FROM defined WHERE id = %s
        """, [word_id])
        return cursor.fetchone()
    except Exception as e:
        print(f"Error fetching word {word_id}: {e}")
        raise Exception(f"Failed to get word by ID: {e}")
    finally:
        connection.close()

@app.get("/word/{word_id}")
async def word_detail(word_id: int):
    """Get word details"""
    word = next((w for w in SAMPLE_WORDS if w["id"] == word_id), None)
    if word:
        return word
    return {"error": "Word not found"}

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse("login.html", {
        "request": request,
        "current_user": None
    })

@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, 
               username: str = Form(...),
               password: str = Form(...),
               remember_me: bool = Form(False)):
    """Handle user login"""
    user = authenticate_user(username, password)
    
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "current_user": None,
            "error": "Invalid username or password"
        })
    
    # Create session
    session_id = create_session(user)
    
    # Create response and set cookie
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    
    # Set session cookie (secure in production)
    cookie_max_age = 60 * 60 * 24 * 30 if remember_me else 60 * 60 * 24  # 30 days or 1 day
    response.set_cookie(
        key="session_id",
        value=session_id,
        max_age=cookie_max_age,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax"
    )
    
    return response

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Register page"""
    current_user = get_current_user(request)
    return templates.TemplateResponse("register.html", {
        "request": request,
        "current_user": current_user
    })

@app.post("/register", response_class=HTMLResponse)
async def register(request: Request,
                  username: str = Form(...),
                  email: str = Form(...),
                  password: str = Form(...),
                  confirm_password: str = Form(...)):
    """Handle user registration"""
    
    # Validation
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "current_user": None,
            "error": "Passwords do not match"
        })
    
    if len(password) < 6:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "current_user": None,
            "error": "Password must be at least 6 characters long"
        })
    
    # Create user
    user_id = create_user(username, email, password)
    
    if not user_id:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "current_user": None,
            "error": "Username or email already exists"
        })
    
    # Auto-login the new user
    user = authenticate_user(username, password)
    if user:
        session_id = create_session(user)
        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="session_id",
            value=session_id,
            max_age=60 * 60 * 24,  # 1 day
            httponly=True,
            secure=False,
            samesite="lax"
        )
        return response
    
    # Fallback - redirect to login
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

@app.get("/logout")
async def logout(request: Request):
    """Handle user logout"""
    session_id = request.cookies.get("session_id")
    
    # Remove session from active sessions
    if session_id and session_id in active_sessions:
        del active_sessions[session_id]
    
    # Redirect to home and clear cookie
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("session_id")
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)