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

@app.get("/browse", response_class=HTMLResponse)
async def browse(request: Request, 
                letters: Optional[str] = Query(None),
                domain: Optional[str] = Query(None),
                part_of_speech: Optional[str] = Query(None),
                search: Optional[str] = Query(None),
                add_to_deck: Optional[int] = Query(None),
                page: int = Query(1),
                per_page: int = Query(50)):
    """Browse words hierarchically by letters with pagination"""
    current_user = await get_optional_current_user(request)
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Build base query with filters
    base_query = """
    SELECT 
        d.id, d.term, d.definition, d.part_of_speech,
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
    
    # Add letter filtering
    if letters:
        base_query += " AND LOWER(d.term) LIKE %s"
        params.append(f"{letters.lower()}%")
    
    # Add domain filtering
    if domain:
        base_query += " AND wd.primary_domain = %s"
        params.append(domain)
    
    # Add part of speech filtering
    if part_of_speech:
        base_query += " AND d.part_of_speech = %s"
        params.append(part_of_speech)
    
    # Add search filtering  
    if search:
        base_query += " AND (LOWER(d.term) LIKE %s OR LOWER(d.definition) LIKE %s)"
        search_param = f"%{search.lower()}%"
        params.extend([search_param, search_param])
    
    # Get total count
    count_query = f"SELECT COUNT(*) FROM ({base_query}) as filtered"
    cursor.execute(count_query, params)
    total_words = cursor.fetchone()[0]
    
    # Get available next letters for navigation
    available_letters = []
    if total_words > 0:
        if not letters:
            # Show first letters
            letter_query = """
            SELECT DISTINCT LOWER(LEFT(d.term, 1)) as first_letter
            FROM defined d
            LEFT JOIN word_domains wd ON d.id = wd.word_id
            WHERE 1=1
            """
            letter_params = []
            if domain:
                letter_query += " AND wd.primary_domain = %s"
                letter_params.append(domain)
            if part_of_speech:
                letter_query += " AND d.part_of_speech = %s"
                letter_params.append(part_of_speech)
            letter_query += " ORDER BY first_letter"
            
        else:
            # Show next possible letters
            next_pos = len(letters) + 1
            letter_query = f"""
            SELECT DISTINCT LOWER(LEFT(d.term, {next_pos})) as next_letters
            FROM defined d
            LEFT JOIN word_domains wd ON d.id = wd.word_id
            WHERE LOWER(d.term) LIKE %s AND LENGTH(d.term) >= {next_pos}
            """
            letter_params = [f"{letters.lower()}%"]
            if domain:
                letter_query += " AND wd.primary_domain = %s"
                letter_params.append(domain)
            if part_of_speech:
                letter_query += " AND d.part_of_speech = %s"
                letter_params.append(part_of_speech)
            letter_query += " ORDER BY next_letters"
        
        cursor.execute(letter_query, letter_params)
        if not letters:
            available_letters = [row[0] for row in cursor.fetchall()]
        else:
            next_letters = [row[0] for row in cursor.fetchall()]
            # Extract just the next character
            available_letters = list(set([nl[len(letters)] for nl in next_letters if len(nl) > len(letters)]))
            available_letters.sort()
    
    # Get words for current page
    offset = (page - 1) * per_page
    words_query = f"{base_query} ORDER BY COALESCE(wfi.frequency_rank, 999999) ASC LIMIT %s OFFSET %s"
    words_params = params + [per_page, offset]
    
    cursor.execute(words_query, words_params)
    results = cursor.fetchall()
    
    words = []
    for row in results:
        from dataclasses import dataclass
        
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
            wav_url: Optional[str] = None
            ipa_transcription: Optional[str] = None
            arpabet_transcription: Optional[str] = None
            syllable_count: Optional[int] = None
            stress_pattern: Optional[str] = None
        
        words.append(Word(
            id=row[0], term=row[1], definition=row[2], part_of_speech=row[3],
            frequency_rank=row[4], independent_frequency=row[5], rarity_percentile=row[6],
            primary_domain=row[7], wav_url=row[8],
            ipa_transcription=row[9], arpabet_transcription=row[10], 
            syllable_count=row[11], stress_pattern=row[12]
        ))
    
    cursor.close()
    conn.close()
    
    # Generate letter path breadcrumb
    letter_path = []
    if letters:
        for i, letter in enumerate(letters):
            letter_path.append({
                'letter': letter,
                'letters': letters[:i+1]
            })
    
    # Pagination calculations
    total_pages = (total_words + per_page - 1) // per_page if total_words > 0 else 1
    has_next = page < total_pages
    has_prev = page > 1
    
    # Generate page numbers for pagination
    start_page = max(1, page - 2)
    end_page = min(total_pages, page + 2)
    page_numbers = list(range(start_page, end_page + 1))
    
    domains = db.get_domains()
    parts_of_speech = db.get_parts_of_speech()
    
    return templates.TemplateResponse("browse.html", {
        "request": request,
        "current_user": current_user,
        "words": words,
        "domains": domains,
        "parts_of_speech": parts_of_speech,
        "domain": domain,
        "part_of_speech": part_of_speech,
        "letters": letters,
        "available_letters": available_letters,
        "letter_path": letter_path,
        "search": search,
        "add_to_deck": add_to_deck,
        "current_page": page,
        "total_pages": total_pages,
        "total_words": total_words,
        "per_page": per_page,
        "has_next": has_next,
        "has_prev": has_prev,
        "next_page": page + 1,
        "prev_page": page - 1,
        "page_numbers": page_numbers
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

# Pronunciation endpoint
@app.get("/pronunciation/{word}")
async def get_pronunciation_audio(word: str):
    """Generate pronunciation audio for a word using Windows SAPI"""
    try:
        import subprocess
        import tempfile
        import os
        from fastapi.responses import FileResponse
        
        # Create temporary wav file
        temp_dir = tempfile.gettempdir()
        wav_file = os.path.join(temp_dir, f"{word}_{hash(word)}.wav")
        
        # Use Windows built-in text-to-speech
        powershell_script = f"""
        Add-Type -AssemblyName System.Speech
        $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
        $synth.SetOutputToWaveFile("{wav_file}")
        $synth.Speak("{word}")
        $synth.Dispose()
        """
        
        # Execute PowerShell script
        result = subprocess.run([
            "powershell", "-Command", powershell_script
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and os.path.exists(wav_file):
            return FileResponse(
                wav_file,
                media_type="audio/wav",
                filename=f"{word}.wav",
                headers={"Cache-Control": "public, max-age=3600"}
            )
        else:
            raise HTTPException(status_code=500, detail="Could not generate pronunciation")
            
    except Exception as e:
        logger.error(f"Pronunciation generation failed for '{word}': {e}")
        raise HTTPException(status_code=500, detail="Pronunciation unavailable")

# Quiz endpoints
@app.get("/quiz", response_class=HTMLResponse)
async def quiz_home(request: Request):
    """Quiz home page"""
    current_user = await get_optional_current_user(request)
    domains = db.get_domains()
    parts_of_speech = db.get_parts_of_speech()
    
    return templates.TemplateResponse("quiz.html", {
        "request": request,
        "current_user": current_user,
        "domains": domains,
        "parts_of_speech": parts_of_speech
    })

@app.post("/quiz/start", response_class=HTMLResponse)
async def start_quiz(request: Request, 
                    difficulty: str = Form("medium"),
                    quiz_type: str = Form("mixed"),
                    domain: Optional[str] = Form(None),
                    num_questions: int = Form(10)):
    """Start a new quiz session"""
    current_user = await get_optional_current_user(request)
    
    # Get random words for quiz
    words = db.search_words(domain=domain if domain != "all" else None, limit=num_questions * 3)
    if len(words) < num_questions:
        # Fallback to all words if domain doesn't have enough
        words = db.search_words(limit=num_questions * 3)
    
    quiz_words = random.sample(words, min(num_questions, len(words)))
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
                question_text = f"True or False: '{word.term}' means '{word.definition}'"
                correct_answer = True
                explanation = f"TRUE: '{word.term}' does mean '{word.definition}'"
            else:
                # Use wrong definition from another word
                distractors = [w for w in words if w.id != word.id and w.part_of_speech == word.part_of_speech]
                if distractors:
                    wrong_word = random.choice(distractors)
                    question_text = f"True or False: '{word.term}' means '{wrong_word.definition}'"
                    correct_answer = False
                    explanation = f"FALSE: '{word.term}' actually means '{word.definition}', not '{wrong_word.definition}'"
                else:
                    # Fallback to multiple choice if no distractors
                    actual_type = "multiple_choice"
        
        if actual_type == "multiple_choice":
            # Create multiple choice question
            distractors = [w for w in words if w.id != word.id and w.part_of_speech == word.part_of_speech]
            distractor_definitions = [d.definition for d in random.sample(distractors, min(3, len(distractors)))]
            
            options = [word.definition] + distractor_definitions
            random.shuffle(options)
            correct_answer = options.index(word.definition)
            question_text = f"What is the definition of '{word.term}'?"
            explanation = f"'{word.term}' means: {word.definition}"
        
        # Add question to list
        question_data = {
            "id": question_id,
            "word_id": word.id,
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
        "current_user": current_user,
        "questions": questions,
        "quiz_type": quiz_type,
        "difficulty": difficulty,
        "session_id": f"session_{random.randint(1000, 9999)}"
    })

# ==========================================
# FLASHCARD FUNCTIONALITY
# ==========================================

@dataclass
class FlashcardDeck:
    id: int
    name: str
    description: str
    user_id: int
    word_count: int
    created_at: str
    study_progress: float = 0.0

@dataclass
class Flashcard:
    id: int
    word_id: int
    deck_id: int
    word: Word
    mastery_level: str = "learning"  # learning, reviewing, mastered
    last_studied: Optional[str] = None
    study_count: int = 0
    success_rate: float = 0.0

class FlashcardDatabase:
    def __init__(self):
        self.config = get_db_config()
    
    def get_connection(self):
        return mysql.connector.connect(**self.config)
    
    def create_flashcard_tables(self):
        """Create flashcard tables if they don't exist"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Flashcard decks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS flashcard_decks (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    user_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_user_decks (user_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            
            # Flashcard deck items table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS flashcard_deck_items (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    deck_id INT NOT NULL,
                    word_id INT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_deck_word (deck_id, word_id),
                    FOREIGN KEY (deck_id) REFERENCES flashcard_decks(id) ON DELETE CASCADE,
                    FOREIGN KEY (word_id) REFERENCES defined(id) ON DELETE CASCADE
                )
            """)
            
            # User flashcard progress table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_flashcard_progress (
                    user_id INT NOT NULL,
                    word_id INT NOT NULL,
                    mastery_level ENUM('learning', 'reviewing', 'mastered') DEFAULT 'learning',
                    study_count INT DEFAULT 0,
                    correct_count INT DEFAULT 0,
                    last_studied TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    next_review TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    interval_days INT DEFAULT 1,
                    ease_factor FLOAT DEFAULT 2.5,
                    PRIMARY KEY (user_id, word_id),
                    INDEX idx_next_review (user_id, next_review),
                    INDEX idx_mastery (user_id, mastery_level),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (word_id) REFERENCES defined(id) ON DELETE CASCADE
                )
            """)
            
            conn.commit()
            logger.info("Flashcard tables created successfully")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating flashcard tables: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def get_user_decks(self, user_id: int) -> List[FlashcardDeck]:
        """Get all flashcard decks for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT fd.id, fd.name, fd.description, fd.user_id, fd.created_at,
                       COUNT(fdi.word_id) as word_count,
                       COALESCE(AVG(CASE 
                           WHEN ufp.mastery_level = 'mastered' THEN 100
                           WHEN ufp.mastery_level = 'reviewing' THEN 60
                           ELSE 20
                       END), 0) as progress
                FROM flashcard_decks fd
                LEFT JOIN flashcard_deck_items fdi ON fd.id = fdi.deck_id
                LEFT JOIN user_flashcard_progress ufp ON fdi.word_id = ufp.word_id AND ufp.user_id = %s
                WHERE fd.user_id = %s
                GROUP BY fd.id, fd.name, fd.description, fd.user_id, fd.created_at
                ORDER BY fd.created_at DESC
            """, (user_id, user_id))
            
            decks = []
            for row in cursor.fetchall():
                decks.append(FlashcardDeck(
                    id=row[0],
                    name=row[1],
                    description=row[2],
                    user_id=row[3],
                    created_at=row[4].isoformat() if row[4] else "",
                    word_count=row[5],
                    study_progress=float(row[6])
                ))
            
            return decks
            
        finally:
            cursor.close()
            conn.close()

    def create_deck(self, user_id: int, name: str, description: str = "") -> int:
        """Create a new flashcard deck"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO flashcard_decks (name, description, user_id)
                VALUES (%s, %s, %s)
            """, (name, description, user_id))
            
            deck_id = cursor.lastrowid
            conn.commit()
            return deck_id
            
        finally:
            cursor.close()
            conn.close()

    def get_user_deck(self, deck_id: int, user_id: int) -> Optional[FlashcardDeck]:
        """Get a specific deck for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT d.id, d.name, d.description, d.user_id, d.created_at,
                       COUNT(fdi.id) as word_count
                FROM flashcard_decks d
                LEFT JOIN flashcard_deck_items fdi ON d.id = fdi.deck_id
                WHERE d.id = %s AND d.user_id = %s
                GROUP BY d.id, d.name, d.description, d.user_id, d.created_at
            """, (deck_id, user_id))
            
            result = cursor.fetchone()
            if result:
                return FlashcardDeck(
                    id=result[0],
                    name=result[1], 
                    description=result[2],
                    user_id=result[3],
                    word_count=result[5],
                    created_at=result[4]
                )
            return None
            
        finally:
            cursor.close()
            conn.close()

    def delete_deck(self, deck_id: int):
        """Delete a flashcard deck and all its cards"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Delete all cards in the deck first
            cursor.execute("DELETE FROM flashcard_deck_items WHERE deck_id = %s", (deck_id,))
            
            # Delete the deck
            cursor.execute("DELETE FROM flashcard_decks WHERE id = %s", (deck_id,))
            
            conn.commit()
            
        finally:
            cursor.close()
            conn.close()

    def add_word_to_deck(self, deck_id: int, word_id: int):
        """Add a word to a flashcard deck"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT IGNORE INTO flashcard_deck_items (deck_id, word_id)
                VALUES (%s, %s)
            """, (deck_id, word_id))
            conn.commit()
            
        finally:
            cursor.close()
            conn.close()

    def get_deck_cards(self, deck_id: int, user_id: int, limit: int = 20) -> List[Flashcard]:
        """Get flashcards for a deck with user progress"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT fdi.word_id, fd.id as deck_id,
                       d.id, d.term, d.definition, d.part_of_speech, d.frequency,
                       wfi.frequency_rank, wfi.independent_frequency, wfi.rarity_percentile,
                       wd.primary_domain, d.wav_url,
                       wp.ipa_transcription, wp.arpabet_transcription, wp.syllable_count, wp.stress_pattern,
                       COALESCE(ufp.mastery_level, 'learning') as mastery_level,
                       ufp.last_studied, ufp.study_count,
                       COALESCE(ufp.correct_count * 100.0 / NULLIF(ufp.study_count, 0), 0) as success_rate
                FROM flashcard_deck_items fdi
                JOIN flashcard_decks fd ON fdi.deck_id = fd.id
                JOIN defined d ON fdi.word_id = d.id
                LEFT JOIN word_frequencies_independent wfi ON d.id = wfi.word_id
                LEFT JOIN word_domains wd ON d.id = wd.word_id
                LEFT JOIN word_phonetics wp ON d.id = wp.word_id
                LEFT JOIN user_flashcard_progress ufp ON d.id = ufp.word_id AND ufp.user_id = %s
                WHERE fdi.deck_id = %s AND fd.user_id = %s
                ORDER BY 
                    CASE ufp.mastery_level 
                        WHEN 'learning' THEN 1 
                        WHEN 'reviewing' THEN 2 
                        WHEN 'mastered' THEN 3 
                        ELSE 0 
                    END,
                    COALESCE(ufp.next_review, NOW())
                LIMIT %s
            """, (user_id, deck_id, user_id, limit))
            
            cards = []
            for row in cursor.fetchall():
                word = Word(
                    id=row[2], term=row[3], definition=row[4], part_of_speech=row[5], 
                    frequency=row[6], frequency_rank=row[7], independent_frequency=row[8],
                    rarity_percentile=row[9], primary_domain=row[10], wav_url=row[11],
                    ipa_transcription=row[12], arpabet_transcription=row[13], 
                    syllable_count=row[14], stress_pattern=row[15]
                )
                
                cards.append(Flashcard(
                    id=row[0], word_id=row[0], deck_id=row[1], word=word,
                    mastery_level=row[16], 
                    last_studied=row[17].isoformat() if row[17] else None,
                    study_count=row[18] or 0,
                    success_rate=float(row[19] or 0.0)
                ))
            
            return cards
            
        finally:
            cursor.close()
            conn.close()

    def update_card_progress(self, user_id: int, word_id: int, is_correct: bool):
        """Update flashcard progress after study session"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Insert or update progress
            cursor.execute("""
                INSERT INTO user_flashcard_progress 
                (user_id, word_id, study_count, correct_count, last_studied, next_review)
                VALUES (%s, %s, 1, %s, NOW(), DATE_ADD(NOW(), INTERVAL 1 DAY))
                ON DUPLICATE KEY UPDATE
                study_count = study_count + 1,
                correct_count = correct_count + %s,
                last_studied = NOW(),
                mastery_level = CASE
                    WHEN correct_count + %s >= study_count + 1 * 0.8 AND study_count + 1 >= 3 THEN 'reviewing'
                    WHEN correct_count + %s >= study_count + 1 * 0.9 AND study_count + 1 >= 5 THEN 'mastered'
                    ELSE mastery_level
                END,
                next_review = CASE
                    WHEN %s = 1 THEN DATE_ADD(NOW(), INTERVAL LEAST(interval_days * 2, 30) DAY)
                    ELSE DATE_ADD(NOW(), INTERVAL 1 DAY)
                END,
                interval_days = CASE
                    WHEN %s = 1 THEN LEAST(interval_days * 2, 30)
                    ELSE GREATEST(interval_days / 2, 1)
                END
            """, (user_id, word_id, 1 if is_correct else 0, 1 if is_correct else 0, 
                  1 if is_correct else 0, 1 if is_correct else 0, 1 if is_correct else 0, 1 if is_correct else 0))
            
            conn.commit()
            
        finally:
            cursor.close()
            conn.close()

    def get_random_cards(self, user_id: int, limit: int = 20) -> List[Flashcard]:
        """Get random words for flashcard study"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT d.id, 0 as deck_id,
                       d.id, d.term, d.definition, d.part_of_speech, d.frequency,
                       wfi.frequency_rank, wfi.independent_frequency, wfi.rarity_percentile,
                       wd.primary_domain, d.wav_url,
                       wp.ipa_transcription, wp.arpabet_transcription, wp.syllable_count, wp.stress_pattern,
                       COALESCE(ufp.mastery_level, 'learning') as mastery_level,
                       ufp.last_studied, ufp.study_count,
                       COALESCE(ufp.correct_count * 100.0 / NULLIF(ufp.study_count, 0), 0) as success_rate
                FROM defined d
                LEFT JOIN word_frequencies_independent wfi ON d.id = wfi.word_id
                LEFT JOIN word_domains wd ON d.id = wd.word_id
                LEFT JOIN word_phonetics wp ON d.id = wp.word_id
                LEFT JOIN user_flashcard_progress ufp ON d.id = ufp.word_id AND ufp.user_id = %s
                WHERE d.definition IS NOT NULL AND d.definition != ''
                ORDER BY RAND()
                LIMIT %s
            """, (user_id, limit))
            
            cards = []
            for row in cursor.fetchall():
                word = Word(
                    id=row[2], term=row[3], definition=row[4], part_of_speech=row[5], 
                    frequency=row[6], frequency_rank=row[7], independent_frequency=row[8],
                    rarity_percentile=row[9], primary_domain=row[10], wav_url=row[11],
                    ipa_transcription=row[12], arpabet_transcription=row[13], 
                    syllable_count=row[14], stress_pattern=row[15]
                )
                
                cards.append(Flashcard(
                    id=row[0], word_id=row[0], deck_id=row[1], word=word,
                    mastery_level=row[16], 
                    last_studied=row[17].isoformat() if row[17] else None,
                    study_count=row[18] or 0,
                    success_rate=float(row[19] or 0.0)
                ))
            
            return cards
            
        finally:
            cursor.close()
            conn.close()

# Initialize flashcard database
flashcard_db = FlashcardDatabase()

# ==========================================
# FLASHCARD API ENDPOINTS
# ==========================================

@app.get("/flashcards", response_class=HTMLResponse)
async def flashcards_home(request: Request, current_user: User = Depends(get_current_active_user)):
    """Flashcards home page - show user's decks"""
    decks = flashcard_db.get_user_decks(current_user.id)
    
    return templates.TemplateResponse("flashcards.html", {
        "request": request,
        "current_user": current_user,
        "decks": decks
    })

@app.post("/api/flashcards/decks")
async def create_flashcard_deck(request: Request,
                               name: str = Form(...),
                               description: str = Form(""),
                               current_user: User = Depends(get_current_active_user)):
    """Create a new flashcard deck"""
    try:
        deck_id = flashcard_db.create_deck(current_user.id, name, description)
        return {"success": True, "deck_id": deck_id}
    except Exception as e:
        logger.error(f"Error creating deck: {e}")
        raise HTTPException(status_code=500, detail="Failed to create deck")

@app.delete("/api/flashcards/decks/{deck_id}")
async def delete_flashcard_deck(deck_id: int, current_user: User = Depends(get_current_active_user)):
    """Delete a flashcard deck"""
    try:
        # Check if deck belongs to current user
        deck = flashcard_db.get_user_deck(deck_id, current_user.id)
        if not deck:
            raise HTTPException(status_code=404, detail="Deck not found")
        
        flashcard_db.delete_deck(deck_id)
        return {"success": True, "message": "Deck deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting deck: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete deck")

@app.get("/api/flashcards/decks")
async def get_user_decks(current_user: User = Depends(get_current_active_user)):
    """Get all decks for the current user"""
    try:
        decks = flashcard_db.get_user_decks(current_user.id)
        # Convert to dict format for JSON response
        deck_list = []
        for deck in decks:
            deck_list.append({
                "id": deck.id,
                "name": deck.name,
                "description": deck.description,
                "word_count": deck.word_count,
                "created_at": deck.created_at.isoformat() if hasattr(deck.created_at, 'isoformat') else str(deck.created_at)
            })
        return {"success": True, "decks": deck_list}
    except Exception as e:
        logger.error(f"Error getting user decks: {e}")
        raise HTTPException(status_code=500, detail="Failed to load decks")

@app.get("/api/flashcards/decks/{deck_id}/cards")
async def get_deck_cards(deck_id: int, current_user: User = Depends(get_current_active_user)):
    """Get cards for a flashcard deck"""
    try:
        cards = flashcard_db.get_deck_cards(deck_id, current_user.id)
        return {"cards": [
            {
                "id": card.id,
                "word_id": card.word_id,
                "term": card.word.term,
                "definition": card.word.definition,
                "part_of_speech": card.word.part_of_speech,
                "ipa_transcription": card.word.ipa_transcription,
                "mastery_level": card.mastery_level,
                "success_rate": card.success_rate,
                "study_count": card.study_count
            } for card in cards
        ]}
    except Exception as e:
        logger.error(f"Error getting deck cards: {e}")
        raise HTTPException(status_code=500, detail="Failed to get deck cards")

@app.post("/api/flashcards/decks/{deck_id}/cards/{word_id}")
async def add_word_to_deck(deck_id: int, word_id: int, 
                          current_user: User = Depends(get_current_active_user)):
    """Add a word to a flashcard deck"""
    try:
        flashcard_db.add_word_to_deck(deck_id, word_id)
        return {"success": True}
    except Exception as e:
        logger.error(f"Error adding word to deck: {e}")
        raise HTTPException(status_code=500, detail="Failed to add word to deck")

@app.post("/api/flashcards/study")
async def study_flashcard(request: Request,
                         word_id: int = Form(...),
                         is_correct: bool = Form(...),
                         current_user: User = Depends(get_current_active_user)):
    """Record flashcard study result"""
    try:
        flashcard_db.update_card_progress(current_user.id, word_id, is_correct)
        return {"success": True}
    except Exception as e:
        logger.error(f"Error updating flashcard progress: {e}")
        raise HTTPException(status_code=500, detail="Failed to update progress")

@app.get("/flashcards/random/study", response_class=HTMLResponse)
async def study_random_cards(request: Request, 
                            limit: int = 20,
                            current_user: User = Depends(get_current_active_user)):
    """Study random flashcards"""
    try:
        cards = flashcard_db.get_random_cards(current_user.id, limit)
        
        if not cards:
            return templates.TemplateResponse("flashcards_empty.html", {
                "request": request,
                "current_user": current_user,
                "deck_id": 0,
                "is_random": True
            })
        
        # Convert cards to dictionaries for template serialization
        serialized_cards = []
        for card in cards:
            serialized_cards.append({
                "id": card.id,
                "word_id": card.word_id,
                "deck_id": 0,  # No specific deck for random cards
                "mastery_level": card.mastery_level,
                "last_studied": card.last_studied,
                "study_count": card.study_count,
                "success_rate": float(card.success_rate) if card.success_rate is not None else 0.0,
                "word": {
                    "id": card.word.id,
                    "term": card.word.term,
                    "definition": card.word.definition,
                    "part_of_speech": card.word.part_of_speech,
                    "frequency": float(card.word.frequency) if card.word.frequency is not None else None,
                    "frequency_rank": card.word.frequency_rank,
                    "independent_frequency": float(card.word.independent_frequency) if card.word.independent_frequency is not None else None,
                    "rarity_percentile": float(card.word.rarity_percentile) if card.word.rarity_percentile is not None else None,
                    "primary_domain": card.word.primary_domain,
                    "wav_url": card.word.wav_url,
                    "ipa_transcription": card.word.ipa_transcription,
                    "arpabet_transcription": card.word.arpabet_transcription,
                    "syllable_count": card.word.syllable_count,
                    "stress_pattern": card.word.stress_pattern
                }
            })
        
        return templates.TemplateResponse("flashcard_study.html", {
            "request": request,
            "current_user": current_user,
            "cards": serialized_cards,
            "deck_id": 0,
            "is_random": True,
            "deck_name": "Random Vocabulary"
        })
        
    except Exception as e:
        logger.error(f"Error loading random study session: {e}")
        raise HTTPException(status_code=500, detail="Failed to load random study session")

@app.get("/flashcards/guest/random", response_class=HTMLResponse)
async def guest_random_flashcards(request: Request, limit: int = 20):
    """Guest access to random flashcards for testing"""
    try:
        # Use existing database connection
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Get random words from defined table (simplified)
        cursor.execute("""
            SELECT id, term, definition, part_of_speech, frequency
            FROM defined
            ORDER BY RAND()
            LIMIT %s
        """, (limit,))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Convert to flashcard-like format
        serialized_cards = []
        for row in results:
            word_data = {
                "id": row[0],
                "term": row[1],
                "definition": row[2],
                "part_of_speech": row[3],
                "frequency": float(row[4]) if row[4] is not None else None,
                "frequency_rank": None,
                "independent_frequency": None,
                "rarity_percentile": None,
                "primary_domain": None,
                "wav_url": None,
                "ipa_transcription": None,
                "arpabet_transcription": None,
                "syllable_count": None,
                "stress_pattern": None
            }
            
            serialized_cards.append({
                "word_id": row[0],
                "deck_id": 0,
                "mastery_level": "learning",
                "study_count": 0,
                "success_rate": 0.0,
                "word": word_data
            })
        
        return templates.TemplateResponse("flashcard_study.html", {
            "request": request,
            "current_user": None,
            "cards": serialized_cards,
            "deck_id": 0,
            "is_random": True,
            "deck_name": "Random Vocabulary (Guest Mode)"
        })
        
    except Exception as e:
        logger.error(f"Error loading guest random study session: {e}")
        raise HTTPException(status_code=500, detail="Failed to load guest study session")

@app.get("/flashcards/{deck_id}/study", response_class=HTMLResponse)
async def study_deck(request: Request, deck_id: int, 
                     current_user: User = Depends(get_current_active_user)):
    """Study a flashcard deck"""
    try:
        cards = flashcard_db.get_deck_cards(deck_id, current_user.id)
        
        if not cards:
            # Redirect back to flashcards page with a message about empty deck
            return templates.TemplateResponse("flashcards.html", {
                "request": request,
                "current_user": current_user,
                "message": "This deck is empty. Add some words to start studying!",
                "message_type": "info"
            })
        
        # Convert cards to dictionaries for template serialization
        serialized_cards = []
        for card in cards:
            serialized_cards.append({
                "id": card.id,
                "word_id": card.word_id,
                "deck_id": card.deck_id,
                "mastery_level": card.mastery_level,
                "last_studied": card.last_studied,
                "study_count": card.study_count,
                "success_rate": float(card.success_rate) if card.success_rate is not None else 0.0,
                "word": {
                    "id": card.word.id,
                    "term": card.word.term,
                    "definition": card.word.definition,
                    "part_of_speech": card.word.part_of_speech,
                    "frequency": float(card.word.frequency) if card.word.frequency is not None else None,
                    "frequency_rank": card.word.frequency_rank,
                    "independent_frequency": float(card.word.independent_frequency) if card.word.independent_frequency is not None else None,
                    "rarity_percentile": float(card.word.rarity_percentile) if card.word.rarity_percentile is not None else None,
                    "primary_domain": card.word.primary_domain,
                    "wav_url": card.word.wav_url,
                    "ipa_transcription": card.word.ipa_transcription,
                    "arpabet_transcription": card.word.arpabet_transcription,
                    "syllable_count": card.word.syllable_count,
                    "stress_pattern": card.word.stress_pattern
                }
            })
        
        return templates.TemplateResponse("flashcard_study.html", {
            "request": request,
            "current_user": current_user,
            "cards": serialized_cards,
            "deck_id": deck_id
        })
        
    except Exception as e:
        logger.error(f"Error loading study session: {e}")
        raise HTTPException(status_code=500, detail="Failed to load study session")

# Candidate Review Routes
@app.get("/candidates", response_class=HTMLResponse)
async def list_candidates(request: Request, 
                          status: str = Query("pending", description="Filter by status"),
                          page: int = Query(1, ge=1, description="Page number"),
                          per_page: int = Query(20, ge=1, le=100, description="Items per page"),
                          current_user: User = Depends(get_current_active_user)):
    """List candidate words for review"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Count total candidates
        count_query = "SELECT COUNT(*) FROM candidate_words WHERE review_status = %s"
        cursor.execute(count_query, (status,))
        total_count = cursor.fetchone()[0]
        
        # Calculate pagination
        total_pages = (total_count + per_page - 1) // per_page
        offset = (page - 1) * per_page
        
        # Get candidates for current page
        cursor.execute("""
            SELECT id, term, source_type, part_of_speech, utility_score,
                   rarity_indicators, context_snippet, raw_definition,
                   etymology_preview, date_discovered, review_status,
                   DATEDIFF(CURRENT_DATE, date_discovered) as days_pending
            FROM candidate_words
            WHERE review_status = %s
            ORDER BY utility_score DESC, date_discovered ASC
            LIMIT %s OFFSET %s
        """, (status, per_page, offset))
        
        candidates = []
        for row in cursor.fetchall():
            candidates.append({
                'id': row[0],
                'term': row[1],
                'source_type': row[2],
                'part_of_speech': row[3],
                'utility_score': float(row[4]) if row[4] else 0,
                'rarity_indicators': row[5],
                'context_snippet': row[6],
                'raw_definition': row[7],
                'etymology_preview': row[8],
                'date_discovered': row[9],
                'review_status': row[10],
                'days_pending': row[11]
            })
        
        # Get review statistics
        cursor.execute("""
            SELECT review_status, COUNT(*) as count
            FROM candidate_words
            GROUP BY review_status
        """)
        stats = {row[0]: row[1] for row in cursor.fetchall()}
        
        cursor.close()
        conn.close()
        
        return templates.TemplateResponse("candidates.html", {
            "request": request,
            "current_user": current_user,
            "candidates": candidates,
            "status": status,
            "page": page,
            "per_page": per_page,
            "total_count": total_count,
            "total_pages": total_pages,
            "stats": stats
        })
        
    except Exception as e:
        logger.error(f"Error loading candidates: {e}")
        raise HTTPException(status_code=500, detail="Failed to load candidates")

@app.get("/candidates/{candidate_id}", response_class=HTMLResponse)
async def view_candidate(request: Request, candidate_id: int,
                        current_user: User = Depends(get_current_active_user)):
    """View detailed candidate information"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, term, source_type, source_reference, part_of_speech, 
                   utility_score, rarity_indicators, context_snippet, raw_definition,
                   etymology_preview, date_discovered, review_status, rejection_reason,
                   notes, created_at, updated_at
            FROM candidate_words
            WHERE id = %s
        """, (candidate_id,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Candidate not found")
        
        candidate = {
            'id': row[0],
            'term': row[1],
            'source_type': row[2],
            'source_reference': row[3],
            'part_of_speech': row[4],
            'utility_score': float(row[5]) if row[5] else 0,
            'rarity_indicators': row[6],
            'context_snippet': row[7],
            'raw_definition': row[8],
            'etymology_preview': row[9],
            'date_discovered': row[10],
            'review_status': row[11],
            'rejection_reason': row[12],
            'notes': row[13],
            'created_at': row[14],
            'updated_at': row[15]
        }
        
        cursor.close()
        conn.close()
        
        return templates.TemplateResponse("candidate_detail.html", {
            "request": request,
            "current_user": current_user,
            "candidate": candidate
        })
        
    except Exception as e:
        logger.error(f"Error loading candidate: {e}")
        raise HTTPException(status_code=500, detail="Failed to load candidate")

@app.post("/candidates/{candidate_id}/review")
async def review_candidate(candidate_id: int,
                          action: str = Form(...),
                          reason: str = Form(None),
                          notes: str = Form(None),
                          current_user: User = Depends(get_current_active_user)):
    """Review a candidate (approve, reject, or needs_info)"""
    try:
        if action not in ['approved', 'rejected', 'needs_info']:
            raise HTTPException(status_code=400, detail="Invalid action")
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE candidate_words 
            SET review_status = %s, rejection_reason = %s, notes = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (action, reason, notes, candidate_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return RedirectResponse(url="/candidates", status_code=303)
        
    except Exception as e:
        logger.error(f"Error reviewing candidate: {e}")
        raise HTTPException(status_code=500, detail="Failed to review candidate")

# Initialize flashcard tables on startup
try:
    flashcard_db.create_flashcard_tables()
except Exception as e:
    logger.warning(f"Could not create flashcard tables: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)