#!/usr/bin/env python3
"""
FastAPI Vocabulary Web Application
Browse and explore vocabulary database with search, filtering, and detailed word views
"""

from fastapi import FastAPI, HTTPException, Query, Request, Form, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Optional, List
import mysql.connector
from config import get_db_config
import random
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta
from auth import (
    user_manager, create_access_token, get_current_active_user, 
    get_current_admin_user, get_optional_current_user, User,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Vocabulary Explorer", description="Browse and explore vocabulary database")

# Setup templates
templates = Jinja2Templates(directory="templates")

@dataclass
class Word:
    id: int
    term: str
    definition: str
    part_of_speech: Optional[str] = None
    frequency_rank: Optional[int] = None
    independent_frequency: Optional[float] = None
    rarity_percentile: Optional[float] = None
    primary_domain: Optional[str] = None
    frequency: Optional[float] = None
    wav_url: Optional[str] = None
    ipa_transcription: Optional[str] = None
    arpabet_transcription: Optional[str] = None
    syllable_count: Optional[int] = None
    stress_pattern: Optional[str] = None

class VocabularyDatabase:
    def __init__(self):
        self.config = get_db_config()
    
    def get_connection(self):
        return mysql.connector.connect(**self.config)
    
    def search_words(self, query: Optional[str] = None, domain: Optional[str] = None, 
                    part_of_speech: Optional[str] = None, min_frequency: Optional[int] = None,
                    max_frequency: Optional[int] = None, limit: int = 50, offset: int = 0) -> List[Word]:
        """Search words with various filters"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Build dynamic query
        sql = """
        SELECT 
            d.id, d.term, d.definition, d.part_of_speech, d.frequency,
            wfi.frequency_rank, wfi.independent_frequency, wfi.rarity_percentile,
            wd.primary_domain, d.wav_url,
            wp.ipa_transcription, wp.arpabet_transcription, wp.syllable_count, wp.stress_pattern
        FROM defined d
        LEFT JOIN word_frequencies_independent wfi ON d.id = wfi.word_id
        LEFT JOIN word_domains wd ON d.id = wd.word_id
        LEFT JOIN word_phonetics wp ON d.id = wp.word_id
        WHERE 1=1
        """
        params = []
        
        if query:
            sql += " AND d.term LIKE %s"
            params.append(f"%{query}%")
        
        if domain:
            sql += " AND wd.primary_domain = %s"
            params.append(domain)
        
        if part_of_speech:
            sql += " AND d.part_of_speech = %s"
            params.append(part_of_speech)
        
        if min_frequency:
            sql += " AND wfi.frequency_rank >= %s"
            params.append(min_frequency)
        
        if max_frequency:
            sql += " AND wfi.frequency_rank <= %s"
            params.append(max_frequency)
        
        sql += " ORDER BY COALESCE(wfi.frequency_rank, 999999) ASC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(sql, params)
        results = cursor.fetchall()
        
        words = []
        for row in results:
            words.append(Word(
                id=row[0], term=row[1], definition=row[2], part_of_speech=row[3], frequency=row[4],
                frequency_rank=row[5], independent_frequency=row[6], rarity_percentile=row[7],
                primary_domain=row[8], wav_url=row[9],
                ipa_transcription=row[10], arpabet_transcription=row[11], 
                syllable_count=row[12], stress_pattern=row[13]
            ))
        
        cursor.close()
        conn.close()
        return words
    
    def get_word_by_id(self, word_id: int) -> Optional[Word]:
        """Get detailed word information by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        sql = """
        SELECT 
            d.id, d.term, d.definition, d.part_of_speech,
            wfi.frequency_rank, wfi.independent_frequency, wfi.rarity_percentile,
            wd.primary_domain, d.wav_url,
            wp.ipa_transcription, wp.arpabet_transcription, wp.syllable_count, wp.stress_pattern
        FROM defined d
        LEFT JOIN word_frequencies_independent wfi ON d.id = wfi.word_id
        LEFT JOIN word_domains wd ON d.id = wd.word_id
        LEFT JOIN word_phonetics wp ON d.id = wp.word_id
        WHERE d.id = %s
        """
        
        cursor.execute(sql, (word_id,))
        result = cursor.fetchone()
        
        if not result:
            cursor.close()
            conn.close()
            return None
        
        word = Word(
            id=result[0], term=result[1], definition=result[2], part_of_speech=result[3],
            frequency_rank=result[4], independent_frequency=result[5], rarity_percentile=result[6],
            primary_domain=result[7], wav_url=result[8],
            ipa_transcription=result[9], arpabet_transcription=result[10], 
            syllable_count=result[11], stress_pattern=result[12]
        )
        
        cursor.close()
        conn.close()
        return word
    
    def get_similar_words(self, word_id: int, limit: int = 10) -> List[tuple]:
        """Get words similar to the given word based on definition similarity"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            sql = """
            SELECT d.id, d.term, ds.cosine_similarity
            FROM definition_similarity ds
            JOIN defined d ON (
                CASE 
                    WHEN ds.word1_id = %s THEN ds.word2_id
                    ELSE ds.word1_id
                END = d.id
            )
            WHERE (ds.word1_id = %s OR ds.word2_id = %s)
            ORDER BY ds.cosine_similarity DESC
            LIMIT %s
            """
            cursor.execute(sql, (word_id, word_id, word_id, limit))
            results = cursor.fetchall()
        except Exception as e:
            logger.warning(f"Could not fetch similar words: {e}")
            results = []
        
        cursor.close()
        conn.close()
        return results
    
    def get_random_word(self) -> Optional[Word]:
        """Get a random word for exploration"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM defined")
        total_count = cursor.fetchone()[0]
        
        # Get random word
        random_offset = random.randint(0, total_count - 1)
        
        sql = """
        SELECT 
            d.id, d.term, d.definition, d.part_of_speech,
            wfi.frequency_rank, wfi.independent_frequency, wfi.rarity_percentile,
            wd.primary_domain, d.wav_url,
            wp.ipa_transcription, wp.arpabet_transcription, wp.syllable_count, wp.stress_pattern
        FROM defined d
        LEFT JOIN word_frequencies_independent wfi ON d.id = wfi.word_id
        LEFT JOIN word_domains wd ON d.id = wd.word_id
        LEFT JOIN word_phonetics wp ON d.id = wp.word_id
        LIMIT 1 OFFSET %s
        """
        
        cursor.execute(sql, (random_offset,))
        result = cursor.fetchone()
        
        word = Word(
            id=result[0], term=result[1], definition=result[2], part_of_speech=result[3],
            frequency_rank=result[4], independent_frequency=result[5], rarity_percentile=result[6],
            primary_domain=result[7], wav_url=result[8],
            ipa_transcription=result[9], arpabet_transcription=result[10], 
            syllable_count=result[11], stress_pattern=result[12]
        )
        
        cursor.close()
        conn.close()
        return word
    
    def get_domains(self) -> List[str]:
        """Get list of all domains for filtering"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        sql = """
        SELECT DISTINCT primary_domain FROM word_domains WHERE primary_domain IS NOT NULL
        ORDER BY 1
        """
        
        cursor.execute(sql)
        results = cursor.fetchall()
        domains = [row[0] for row in results if row[0]]
        
        cursor.close()
        conn.close()
        return domains
    
    def get_parts_of_speech(self) -> List[str]:
        """Get list of all parts of speech for filtering"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT DISTINCT part_of_speech FROM defined WHERE part_of_speech IS NOT NULL ORDER BY part_of_speech")
        results = cursor.fetchall()
        parts = [row[0] for row in results if row[0]]
        
        cursor.close()
        conn.close()
        return parts

# Initialize database
db = VocabularyDatabase()

# API Endpoints
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page with search interface"""
    current_user = await get_optional_current_user(request)
    domains = db.get_domains()
    parts_of_speech = db.get_parts_of_speech()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "domains": domains,
        "parts_of_speech": parts_of_speech,
        "current_user": current_user
    })

@app.get("/api/words")
async def search_words(
    q: Optional[str] = Query(None, description="Search query"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    part_of_speech: Optional[str] = Query(None, description="Filter by part of speech"),
    min_frequency: Optional[int] = Query(None, description="Minimum frequency rank"),
    max_frequency: Optional[int] = Query(None, description="Maximum frequency rank"),
    limit: int = Query(50, description="Number of results"),
    offset: int = Query(0, description="Offset for pagination")
):
    """Search words with filters"""
    try:
        words = db.search_words(q, domain, part_of_speech, min_frequency, max_frequency, limit, offset)
        return {"words": words, "total": len(words)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/words/{word_id}")
async def get_word(word_id: int):
    """Get detailed word information"""
    word = db.get_word_by_id(word_id)
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")
    
    # Get similar words
    similar_words = db.get_similar_words(word_id)
    
    return {
        "word": word,
        "similar_words": similar_words
    }

@app.get("/api/random")
async def get_random_word():
    """Get a random word for exploration"""
    word = db.get_random_word()
    if not word:
        raise HTTPException(status_code=404, detail="No words found")
    return {"word": word}

@app.get("/word/{word_id}", response_class=HTMLResponse)
async def word_detail(request: Request, word_id: int):
    """Detailed word page"""
    current_user = await get_optional_current_user(request)
    word = db.get_word_by_id(word_id)
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")
    
    similar_words = db.get_similar_words(word_id)
    
    return templates.TemplateResponse("word_detail.html", {
        "request": request,
        "word": word,
        "similar_words": similar_words,
        "current_user": current_user
    })

@app.get("/random", response_class=HTMLResponse)
async def random_word_page(request: Request):
    """Random word exploration page"""
    current_user = await get_optional_current_user(request)
    word = db.get_random_word()
    similar_words = db.get_similar_words(word.id) if word else []
    
    return templates.TemplateResponse("word_detail.html", {
        "request": request,
        "word": word,
        "similar_words": similar_words,
        "is_random": True,
        "current_user": current_user
    })

# Authentication endpoints
@app.get("/register", response_class=HTMLResponse)
async def register_form(request: Request):
    """Registration form"""
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register", response_class=HTMLResponse)
async def register(request: Request, username: str = Form(...), email: str = Form(...), 
                  full_name: Optional[str] = Form(None), password: str = Form(...), 
                  confirm_password: str = Form(...)):
    """Process user registration"""
    
    # Validation
    errors = []
    
    # Username validation
    if not re.match(r'^[a-zA-Z0-9_]{3,50}$', username):
        errors.append("Username must be 3-50 characters and contain only letters, numbers, and underscores")
    
    # Password validation
    if len(password) < 6:
        errors.append("Password must be at least 6 characters long")
    
    if password != confirm_password:
        errors.append("Passwords do not match")
    
    if errors:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "; ".join(errors),
            "username": username,
            "email": email,
            "full_name": full_name
        })
    
    try:
        # Create user
        user = user_manager.create_user(username, email, password, full_name)
        return templates.TemplateResponse("login.html", {
            "request": request,
            "success": "Account created successfully! Please sign in.",
            "username": username
        })
    except ValueError as e:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": str(e),
            "username": username,
            "email": email,
            "full_name": full_name
        })
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "An error occurred during registration. Please try again.",
            "username": username,
            "email": email,
            "full_name": full_name
        })

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    """Login form"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), 
               remember_me: bool = Form(False)):
    """Process user login"""
    user = user_manager.authenticate_user(username, password)
    
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password",
            "username": username
        })
    
    # Create access token
    token_expires = timedelta(days=30) if remember_me else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=token_expires
    )
    
    # Redirect to home page
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token", 
        value=f"Bearer {access_token}", 
        max_age=int(token_expires.total_seconds()) if remember_me else None,
        httponly=True,
        secure=False  # Set to True in production with HTTPS
    )
    return response

@app.get("/logout")
async def logout(request: Request):
    """User logout"""
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response

@app.get("/profile", response_class=HTMLResponse)
async def profile_form(request: Request):
    """User profile page"""
    current_user = await get_current_active_user(request)
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": current_user
    })

@app.post("/profile", response_class=HTMLResponse)
async def update_profile(request: Request,
                        email: str = Form(...), full_name: Optional[str] = Form(None),
                        current_password: Optional[str] = Form(None), 
                        new_password: Optional[str] = Form(None),
                        confirm_new_password: Optional[str] = Form(None)):
    """Update user profile"""
    current_user = await get_current_active_user(request)
    
    errors = []
    
    # Password change validation
    if new_password:
        if not current_password:
            errors.append("Current password is required to set a new password")
        elif not user_manager.verify_password(current_password, user_manager.get_user_by_id(current_user.id).__dict__.get('password_hash', '')):
            # Get current password hash for verification
            conn = user_manager.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT password_hash FROM users WHERE id = %s", (current_user.id,))
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if not result or not user_manager.verify_password(current_password, result[0]):
                errors.append("Current password is incorrect")
        
        if len(new_password) < 6:
            errors.append("New password must be at least 6 characters long")
        
        if new_password != confirm_new_password:
            errors.append("New passwords do not match")
    
    if errors:
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "user": current_user,
            "error": "; ".join(errors)
        })
    
    try:
        # Update user
        update_data = {"email": email, "full_name": full_name}
        if new_password:
            update_data["password"] = new_password
        
        updated_user = user_manager.update_user(current_user.id, **update_data)
        
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "user": updated_user,
            "success": "Profile updated successfully!"
        })
    except Exception as e:
        logger.error(f"Profile update error: {e}")
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "user": current_user,
            "error": "An error occurred while updating your profile. Please try again."
        })

# Admin endpoints
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Admin dashboard"""
    current_user = await get_current_admin_user(request)
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        # Get user statistics
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = TRUE")
        active_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        admin_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM defined")
        total_words = cursor.fetchone()[0]
        
        # Get recent users
        cursor.execute(
            "SELECT id, username, email, full_name, role, is_active, created_at, last_login_at "
            "FROM users ORDER BY created_at DESC LIMIT 10"
        )
        user_results = cursor.fetchall()
        recent_users = []
        for row in user_results:
            recent_users.append(User(
                id=row[0], username=row[1], email=row[2], full_name=row[3],
                role=row[4], is_active=row[5], created_at=row[6], last_login_at=row[7]
            ))
        
        stats = {
            "total_users": total_users,
            "active_users": active_users,
            "admin_users": admin_users,
            "total_words": total_words,
            "database_name": db.config["database"]
        }
        
        return templates.TemplateResponse("admin_dashboard.html", {
            "request": request,
            "current_user": current_user,
            "stats": stats,
            "recent_users": recent_users,
            "current_time": datetime.now()
        })
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)