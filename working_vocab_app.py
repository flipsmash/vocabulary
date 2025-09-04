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
import json

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
    """Search for words in database"""
    current_user = get_current_user(request)
    
    connection = get_db_connection()
    if not connection:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "current_user": current_user,
            "words": [],
            "query": q,
            "domains": DOMAINS,
            "parts_of_speech": PARTS_OF_SPEECH,
            "error": "Database connection failed"
        })
    
    try:
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        
        if q:
            # Search in both term and definition
            query = """
                SELECT id, term, definition, part_of_speech, frequency
                FROM defined 
                WHERE term LIKE %s OR definition LIKE %s
                ORDER BY frequency DESC
                LIMIT 100
            """
            search_term = f"%{q}%"
            cursor.execute(query, [search_term, search_term])
        else:
            # Show first 20 words if no search query
            query = """
                SELECT id, term, definition, part_of_speech, frequency
                FROM defined 
                ORDER BY term ASC
                LIMIT 20
            """
            cursor.execute(query)
        
        results = cursor.fetchall()
        
        return templates.TemplateResponse("index.html", {
            "request": request,
            "current_user": current_user,
            "words": results,
            "query": q,
            "domains": DOMAINS,
            "parts_of_speech": PARTS_OF_SPEECH
        })
        
    except Exception as e:
        print(f"Search query failed: {e}")
        return templates.TemplateResponse("index.html", {
            "request": request,
            "current_user": current_user,
            "words": [],
            "query": q,
            "domains": DOMAINS,
            "parts_of_speech": PARTS_OF_SPEECH,
            "error": f"Search failed: {e}"
        })
    finally:
        connection.close()

@app.get("/browse", response_class=HTMLResponse)
async def browse_words(request: Request, 
                      page: int = Query(1, ge=1),
                      part_of_speech: str = Query("", alias="pos"),
                      domain: str = Query(""),
                      sort_by: str = Query("term"),
                      per_page: int = Query(50)):
    """Browse vocabulary words with pagination and filtering"""
    current_user = get_current_user(request)
    
    connection = get_db_connection()
    if not connection:
        return templates.TemplateResponse("browse.html", {
            "request": request,
            "current_user": current_user,
            "words": [],
            "error": "Database connection failed",
            "current_page": 1,
            "total_pages": 1,
            "total_words": 0,
            "page_numbers": [1],
            "per_page": per_page,
            "has_prev": False,
            "has_next": False,
            "part_of_speech": part_of_speech,
            "domain": domain,
            "parts_of_speech": PARTS_OF_SPEECH,
            "domains": DOMAINS
        })
    
    try:
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        
        # Build query with filters
        where_conditions = []
        params = []
        
        if part_of_speech:
            where_conditions.append("part_of_speech = %s")
            params.append(part_of_speech)
        
        # Note: domain filtering not available in current schema, but keeping parameter for future
        
        where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Count total records for pagination
        count_query = f"SELECT COUNT(*) FROM defined{where_clause}"
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()['COUNT(*)']
        
        # Calculate pagination  
        offset = (page - 1) * per_page
        total_pages = (total_count + per_page - 1) // per_page
        
        # Generate page numbers for pagination (show 5 pages around current)
        page_numbers = []
        start_page = max(1, page - 2)
        end_page = min(total_pages + 1, page + 3)
        page_numbers = list(range(start_page, end_page))
        
        # Get words for current page
        sort_column = "term" if sort_by == "term" else "frequency"
        sort_order = "ASC" if sort_by == "term" else "DESC"  # Frequency: higher number = more common
        
        query = f"""
            SELECT id, term, definition, part_of_speech, frequency
            FROM defined
            {where_clause}
            ORDER BY {sort_column} {sort_order}
            LIMIT %s OFFSET %s
        """
        params.extend([per_page, offset])
        
        cursor.execute(query, params)
        words = cursor.fetchall()
        
        # Calculate frequency ranks (approximate)
        for word in words:
            if word.get('frequency'):
                # Convert frequency to approximate rank (lower frequency = higher rank number)
                word['frequency_rank'] = int(22000 - (word['frequency'] * 1000)) if word['frequency'] else None
        
        return templates.TemplateResponse("browse.html", {
            "request": request,
            "current_user": current_user,
            "words": words,
            "current_page": page,
            "total_pages": total_pages,
            "total_words": total_count,
            "page_numbers": page_numbers,
            "per_page": per_page,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_page": page - 1 if page > 1 else None,
            "next_page": page + 1 if page < total_pages else None,
            "part_of_speech": part_of_speech,
            "domain": domain,
            "sort_by": sort_by,
            "parts_of_speech": PARTS_OF_SPEECH,
            "domains": DOMAINS
        })
        
    except Exception as e:
        print(f"Browse query failed: {e}")
        return templates.TemplateResponse("browse.html", {
            "request": request,
            "current_user": current_user,
            "words": [],
            "error": f"Failed to browse words: {e}",
            "current_page": 1,
            "total_pages": 1,
            "total_words": 0,
            "page_numbers": [1],
            "per_page": per_page,
            "has_prev": False,
            "has_next": False,
            "part_of_speech": part_of_speech,
            "domain": domain,
            "parts_of_speech": PARTS_OF_SPEECH,
            "domains": DOMAINS
        })
    finally:
        connection.close()

@app.get("/random", response_class=HTMLResponse)
async def random_word(request: Request):
    """Show a random vocabulary word"""
    current_user = get_current_user(request)
    
    connection = get_db_connection()
    if not connection:
        return templates.TemplateResponse("word_detail.html", {
            "request": request,
            "current_user": current_user,
            "error": "Database connection failed"
        })
    
    try:
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        
        # Get a random word from the database
        query = """
            SELECT id, term, definition, part_of_speech, frequency
            FROM defined 
            ORDER BY RAND()
            LIMIT 1
        """
        cursor.execute(query)
        word = cursor.fetchone()
        
        if word:
            return templates.TemplateResponse("word_detail.html", {
                "request": request,
                "current_user": current_user,
                "word": word
            })
        else:
            return templates.TemplateResponse("word_detail.html", {
                "request": request,
                "current_user": current_user,
                "error": "No words found in database"
            })
        
    except Exception as e:
        print(f"Random word query failed: {e}")
        return templates.TemplateResponse("word_detail.html", {
            "request": request,
            "current_user": current_user,
            "error": f"Failed to get random word: {e}"
        })
    finally:
        connection.close()

@app.get("/quiz", response_class=HTMLResponse)
async def quiz_home(request: Request):
    """Quiz home page - requires authentication"""
    current_user = get_current_user(request)
    if not current_user:
        return RedirectResponse(url="/login?next=/quiz", status_code=302)
    
    return templates.TemplateResponse("quiz.html", {
        "request": request,
        "current_user": current_user,
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
    """Start a working quiz - requires authentication"""
    current_user = get_current_user(request)
    if not current_user:
        return RedirectResponse(url="/login?next=/quiz", status_code=302)
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
    
    # Generate unique session ID and save to database
    session_id = secrets.token_urlsafe(16)
    quiz_config = {
        "quiz_type": quiz_type,
        "difficulty": difficulty,
        "domain": domain,
        "part_of_speech": part_of_speech,
        "num_questions": num_questions
    }
    
    # Save quiz session to database
    save_quiz_session(session_id, current_user.id, quiz_config)
    
    return templates.TemplateResponse("quiz_session.html", {
        "request": request,
        "current_user": current_user,
        "questions": questions,
        "quiz_type": quiz_type,
        "difficulty": difficulty,
        "session_id": session_id
    })

@app.post("/quiz/submit", response_class=HTMLResponse)
async def submit_quiz(request: Request,
                     session_id: str = Form(...),
                     results: str = Form(...)):
    """Handle quiz submission and show results summary - requires authentication"""
    current_user = get_current_user(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)
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
                
                # Save individual quiz result to database
                response_time = question_result.get('response_time_ms', 3000)  # Default 3 seconds
                save_quiz_result(
                    user_id=current_user.id,
                    word_id=word_id,
                    question_type=question_type,
                    is_correct=is_correct,
                    response_time_ms=response_time,
                    difficulty=difficulty
                )
                
                # Update word mastery tracking
                update_word_mastery(current_user.id, word_id, is_correct)
        
        # Complete quiz session in database
        complete_quiz_session(session_id, correct_count)
        
        print(f"Quiz completed and saved - Session: {session_id}, User: {current_user.id}, Accuracy: {accuracy}%")
        
        return templates.TemplateResponse("quiz_results.html", {
            "request": request,
            "current_user": current_user,
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

# Quiz data storage functions
def save_quiz_session(session_id: str, user_id: int, quiz_config: dict) -> bool:
    """Save quiz session to database"""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO quiz_sessions 
            (id, user_id, started_at, quiz_type, difficulty, topic_domain, topic_pos, 
             total_questions, session_config)
            VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s, %s)
        """, (
            session_id, 
            user_id,
            quiz_config.get('quiz_type', 'mixed'),
            quiz_config.get('difficulty', 'medium'),
            quiz_config.get('domain', ''),
            quiz_config.get('part_of_speech', ''),
            quiz_config.get('num_questions', 5),
            json.dumps(quiz_config)
        ))
        connection.commit()
        return True
    except Exception as e:
        print(f"Error saving quiz session: {e}")
        connection.rollback()
        return False
    finally:
        connection.close()

def complete_quiz_session(session_id: str, correct_count: int) -> bool:
    """Mark quiz session as completed"""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE quiz_sessions 
            SET completed_at = NOW(), correct_answers = %s
            WHERE id = %s
        """, (correct_count, session_id))
        connection.commit()
        return True
    except Exception as e:
        print(f"Error completing quiz session: {e}")
        connection.rollback()
        return False
    finally:
        connection.close()

def save_quiz_result(user_id: int, word_id: int, question_type: str, is_correct: bool, 
                    response_time_ms: int, difficulty: str) -> bool:
    """Save individual quiz result"""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO user_quiz_results 
            (user_id, word_id, question_type, is_correct, response_time_ms, 
             answered_at, difficulty_level)
            VALUES (%s, %s, %s, %s, %s, NOW(), %s)
        """, (user_id, word_id, question_type, is_correct, response_time_ms, difficulty))
        connection.commit()
        return True
    except Exception as e:
        print(f"Error saving quiz result: {e}")
        connection.rollback()
        return False
    finally:
        connection.close()

def update_word_mastery(user_id: int, word_id: int, is_correct: bool) -> bool:
    """Update word mastery tracking with spaced repetition logic"""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        
        # Check if mastery record exists
        cursor.execute("""
            SELECT total_attempts, correct_attempts, streak, ease_factor, mastery_level
            FROM user_word_mastery 
            WHERE user_id = %s AND word_id = %s
        """, (user_id, word_id))
        
        existing = cursor.fetchone()
        
        if existing:
            # Update existing record
            total_attempts, correct_attempts, streak, ease_factor, mastery_level = existing
            total_attempts += 1
            
            if is_correct:
                correct_attempts += 1
                streak += 1
                ease_factor = min(2.5, ease_factor + 0.1)  # Increase ease on success
            else:
                streak = 0
                ease_factor = max(1.3, ease_factor - 0.2)  # Decrease ease on failure
            
            # Update mastery level based on performance
            accuracy = correct_attempts / total_attempts if total_attempts > 0 else 0
            if accuracy >= 0.9 and total_attempts >= 3:
                mastery_level = 'mastered'
            elif accuracy >= 0.7:
                mastery_level = 'reviewing'
            else:
                mastery_level = 'learning'
            
            # Calculate next review time (spaced repetition)
            from datetime import datetime, timedelta
            if is_correct:
                days_ahead = int(streak * ease_factor)  # More successful = longer intervals
                next_review = datetime.now() + timedelta(days=max(1, days_ahead))
            else:
                next_review = datetime.now() + timedelta(hours=1)  # Review failed words sooner
            
            cursor.execute("""
                UPDATE user_word_mastery 
                SET total_attempts = %s, correct_attempts = %s, streak = %s, 
                    ease_factor = %s, mastery_level = %s, last_seen = NOW(), 
                    next_review = %s
                WHERE user_id = %s AND word_id = %s
            """, (total_attempts, correct_attempts, streak, ease_factor, 
                  mastery_level, next_review, user_id, word_id))
        else:
            # Create new record
            from datetime import datetime, timedelta
            correct_attempts = 1 if is_correct else 0
            streak = 1 if is_correct else 0
            ease_factor = 2.0
            mastery_level = 'learning'
            next_review = datetime.now() + timedelta(days=1 if is_correct else 0, hours=1 if not is_correct else 0)
            
            cursor.execute("""
                INSERT INTO user_word_mastery 
                (user_id, word_id, mastery_level, total_attempts, correct_attempts, 
                 last_seen, next_review, streak, ease_factor)
                VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s, %s)
            """, (user_id, word_id, mastery_level, 1, correct_attempts, 
                  next_review, streak, ease_factor))
        
        connection.commit()
        return True
    except Exception as e:
        print(f"Error updating word mastery: {e}")
        connection.rollback()
        return False
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

@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    """Analytics page showing user's vocabulary learning progress"""
    current_user = get_current_user(request)
    if not current_user:
        return RedirectResponse(url="/login?next=/analytics", status_code=302)
    
    try:
        connection = get_db_connection()
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        
        # Get overall stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_sessions,
                SUM(correct_answers) as total_correct,
                SUM(total_questions) as total_questions,
                AVG(correct_answers / total_questions * 100) as avg_accuracy
            FROM quiz_sessions 
            WHERE user_id = %s AND completed_at IS NOT NULL
        """, (current_user.id,))
        
        overall_stats = cursor.fetchone()
        if overall_stats and overall_stats['total_questions']:
            total_sessions = overall_stats['total_sessions'] or 0
            total_correct = overall_stats['total_correct'] or 0
            total_questions = overall_stats['total_questions'] or 0
            avg_accuracy = overall_stats['avg_accuracy'] or 0
        else:
            total_sessions = total_correct = total_questions = avg_accuracy = 0
        
        # Get recent quiz performance (last 10 sessions)
        cursor.execute("""
            SELECT 
                DATE(completed_at) as quiz_date,
                quiz_type,
                difficulty,
                total_questions,
                correct_answers,
                (correct_answers / total_questions * 100) as accuracy,
                completed_at
            FROM quiz_sessions 
            WHERE user_id = %s AND completed_at IS NOT NULL
            ORDER BY completed_at DESC 
            LIMIT 10
        """, (current_user.id,))
        
        recent_sessions = list(cursor.fetchall())
        
        # Get word mastery stats
        cursor.execute("""
            SELECT 
                mastery_level,
                COUNT(*) as word_count
            FROM user_word_mastery 
            WHERE user_id = %s 
            GROUP BY mastery_level
            ORDER BY mastery_level DESC
        """, (current_user.id,))
        
        mastery_stats = {row['mastery_level']: row['word_count'] for row in cursor.fetchall()}
        
        # Get words that need review (due for spaced repetition)
        cursor.execute("""
            SELECT COUNT(*) as words_to_review
            FROM user_word_mastery 
            WHERE user_id = %s AND next_review <= NOW()
        """, (current_user.id,))
        
        words_to_review = cursor.fetchone()['words_to_review'] or 0
        
        # Get most challenging words (lowest accuracy)
        cursor.execute("""
            SELECT 
                d.term,
                d.definition,
                d.part_of_speech,
                uwm.total_attempts,
                uwm.correct_attempts,
                (uwm.correct_attempts / uwm.total_attempts * 100) as accuracy,
                uwm.mastery_level
            FROM user_word_mastery uwm
            JOIN defined d ON uwm.word_id = d.id
            WHERE uwm.user_id = %s AND uwm.total_attempts >= 2
            ORDER BY (uwm.correct_attempts / uwm.total_attempts) ASC, uwm.total_attempts DESC
            LIMIT 10
        """, (current_user.id,))
        
        challenging_words = list(cursor.fetchall())
        
        # Get strongest words (highest accuracy with multiple attempts)
        cursor.execute("""
            SELECT 
                d.term,
                d.definition,
                d.part_of_speech,
                uwm.total_attempts,
                uwm.correct_attempts,
                (uwm.correct_attempts / uwm.total_attempts * 100) as accuracy,
                uwm.mastery_level,
                uwm.streak
            FROM user_word_mastery uwm
            JOIN defined d ON uwm.word_id = d.id
            WHERE uwm.user_id = %s AND uwm.total_attempts >= 3
            ORDER BY (uwm.correct_attempts / uwm.total_attempts) DESC, uwm.streak DESC, uwm.total_attempts DESC
            LIMIT 10
        """, (current_user.id,))
        
        strongest_words = list(cursor.fetchall())
        
        # Get learning streak data
        cursor.execute("""
            SELECT 
                DATE(completed_at) as quiz_date,
                COUNT(*) as sessions_count
            FROM quiz_sessions 
            WHERE user_id = %s AND completed_at IS NOT NULL
            GROUP BY DATE(completed_at)
            ORDER BY DATE(completed_at) DESC
            LIMIT 30
        """, (current_user.id,))
        
        daily_activity = list(cursor.fetchall())
        
        # Calculate current learning streak
        current_streak = 0
        if daily_activity:
            from datetime import datetime, timedelta
            today = datetime.now().date()
            
            # Check if user studied today or yesterday
            last_study = daily_activity[0]['quiz_date']
            if last_study == today or last_study == (today - timedelta(days=1)):
                # Count consecutive days backwards
                expected_date = last_study
                for activity in daily_activity:
                    if activity['quiz_date'] == expected_date:
                        current_streak += 1
                        expected_date -= timedelta(days=1)
                    else:
                        break
        
        # Get difficulty distribution
        cursor.execute("""
            SELECT 
                difficulty,
                COUNT(*) as session_count,
                AVG(correct_answers / total_questions * 100) as avg_accuracy
            FROM quiz_sessions 
            WHERE user_id = %s AND completed_at IS NOT NULL
            GROUP BY difficulty
        """, (current_user.id,))
        
        difficulty_stats = {row['difficulty']: {'count': row['session_count'], 'accuracy': row['avg_accuracy'] or 0} 
                          for row in cursor.fetchall()}
        
        connection.close()
        
        return templates.TemplateResponse("analytics.html", {
            "request": request,
            "current_user": current_user,
            "total_sessions": total_sessions,
            "total_correct": total_correct,
            "total_questions": total_questions,
            "avg_accuracy": round(avg_accuracy, 1) if avg_accuracy else 0,
            "recent_sessions": recent_sessions,
            "mastery_stats": mastery_stats,
            "words_to_review": words_to_review,
            "challenging_words": challenging_words,
            "strongest_words": strongest_words,
            "daily_activity": daily_activity,
            "current_streak": current_streak,
            "difficulty_stats": difficulty_stats
        })
        
    except Exception as e:
        print(f"Analytics error: {e}")
        return templates.TemplateResponse("analytics.html", {
            "request": request,
            "current_user": current_user,
            "error": "Unable to load analytics data. Please try again later.",
            "total_sessions": 0,
            "total_correct": 0,
            "total_questions": 0,
            "avg_accuracy": 0,
            "recent_sessions": [],
            "mastery_stats": {},
            "words_to_review": 0,
            "challenging_words": [],
            "strongest_words": [],
            "daily_activity": [],
            "current_streak": 0,
            "difficulty_stats": {}
        })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)