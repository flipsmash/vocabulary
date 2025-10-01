#!/usr/bin/env python3
"""
FastAPI Vocabulary Web Application
Browse and explore vocabulary database with search, filtering, and detailed word views
"""

from fastapi import FastAPI, HTTPException, Query, Request, Form, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Optional, List, Any
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.secure_config import get_db_config
from core.database_manager import db_manager, database_cursor
import random
import time
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta
from core.auth import (
    user_manager, create_access_token, get_current_active_user,
    get_current_admin_user, get_optional_current_user, User,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from core.quiz_tracking import quiz_tracker, QuestionType, DifficultyLevel
from core.analytics import analytics
import re
from core.comprehensive_definition_lookup import ComprehensiveDefinitionLookup
import asyncio
from psycopg import errors as pg_errors

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Vocabulary Explorer", description="Browse and explore vocabulary database")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount pronunciation files (audio)
app.mount("/pronunciation", StaticFiles(directory="pronunciation_files"), name="pronunciation")

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
    obsolete_or_archaic: Optional[bool] = None

class VocabularyDatabase:
    def __init__(self):
        self.config = get_db_config()

    def search_words(
        self,
        query: Optional[str] = None,
        domain: Optional[str] = None,
        part_of_speech: Optional[str] = None,
        min_frequency: Optional[int] = None,
        max_frequency: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Word]:
        sql = """
        SELECT
            d.id, d.term, d.definition, d.part_of_speech, d.frequency,
            wfi.frequency_rank, wfi.independent_frequency, wfi.rarity_percentile,
            wd.primary_domain, d.wav_url,
            wp.ipa_transcription, wp.arpabet_transcription, wp.syllable_count, wp.stress_pattern,
            d.obsolete_or_archaic
        FROM defined d
        LEFT JOIN word_frequencies_independent wfi ON d.id = wfi.word_id
        LEFT JOIN word_domains wd ON d.id = wd.word_id
        LEFT JOIN word_phonetics wp ON d.id = wp.word_id
        WHERE 1=1
        """
        params: List[Any] = []

        if query:
            sql += " AND d.term ILIKE %s"
            params.append(f"%{query}%")

        if domain:
            sql += " AND wd.primary_domain = %s"
            params.append(domain)

        if part_of_speech:
            sql += " AND d.part_of_speech = %s"
            params.append(part_of_speech)

        if min_frequency is not None:
            sql += " AND wfi.frequency_rank >= %s"
            params.append(min_frequency)

        if max_frequency is not None:
            sql += " AND wfi.frequency_rank <= %s"
            params.append(max_frequency)

        sql += " ORDER BY LOWER(d.term) ASC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        with db_manager.get_cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        return [
            Word(
                id=row[0],
                term=row[1],
                definition=row[2],
                part_of_speech=row[3],
                frequency=row[4],
                frequency_rank=row[5],
                independent_frequency=row[6],
                rarity_percentile=row[7],
                primary_domain=row[8],
                wav_url=row[9],
                ipa_transcription=row[10],
                arpabet_transcription=row[11],
                syllable_count=row[12],
                stress_pattern=row[13],
                obsolete_or_archaic=row[14],
            )
            for row in rows
        ]

    def get_word_by_id(self, word_id: int) -> Optional[Word]:
        sql = """
        SELECT
            d.id, d.term, d.definition, d.part_of_speech,
            wfi.frequency_rank, wfi.independent_frequency, wfi.rarity_percentile,
            wd.primary_domain, d.wav_url,
            wp.ipa_transcription, wp.arpabet_transcription, wp.syllable_count, wp.stress_pattern,
            d.obsolete_or_archaic
        FROM defined d
        LEFT JOIN word_frequencies_independent wfi ON d.id = wfi.word_id
        LEFT JOIN word_domains wd ON d.id = wd.word_id
        LEFT JOIN word_phonetics wp ON d.id = wp.word_id
        WHERE d.id = %s
        """

        with db_manager.get_cursor() as cursor:
            cursor.execute(sql, (word_id,))
            result = cursor.fetchone()

        if not result:
            return None

        return Word(
            id=result[0],
            term=result[1],
            definition=result[2],
            part_of_speech=result[3],
            frequency_rank=result[4],
            independent_frequency=result[5],
            rarity_percentile=result[6],
            primary_domain=result[7],
            wav_url=result[8],
            ipa_transcription=result[9],
            arpabet_transcription=result[10],
            syllable_count=result[11],
            stress_pattern=result[12],
            obsolete_or_archaic=result[13],
        )

    def get_similar_words(self, word_id: int, limit: int = 10) -> List[tuple]:
        sql = """
        SELECT d.id, d.term, ds.cosine_similarity
        FROM definition_similarity ds
        JOIN defined d ON (
            CASE WHEN ds.word1_id = %s THEN ds.word2_id ELSE ds.word1_id END = d.id
        )
        WHERE (ds.word1_id = %s OR ds.word2_id = %s)
        ORDER BY ds.cosine_similarity DESC
        LIMIT %s
        """

        with db_manager.get_cursor() as cursor:
            try:
                cursor.execute(sql, (word_id, word_id, word_id, limit))
                return cursor.fetchall()
            except Exception as exc:
                logger.warning(f"Could not fetch similar words: {exc}")
                return []

    def get_random_word(self) -> Optional[Word]:
        with db_manager.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM defined")
            total_count = cursor.fetchone()[0]
            if not total_count:
                return None

            random_offset = random.randint(0, max(total_count - 1, 0))

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

        if not result:
            return None

        return Word(
            id=result[0],
            term=result[1],
            definition=result[2],
            part_of_speech=result[3],
            frequency_rank=result[4],
            independent_frequency=result[5],
            rarity_percentile=result[6],
            primary_domain=result[7],
            wav_url=result[8],
            ipa_transcription=result[9],
            arpabet_transcription=result[10],
            syllable_count=result[11],
            stress_pattern=result[12],
            obsolete_or_archaic=result[13],
        )

    def get_domains(self) -> List[str]:
        sql = """
        SELECT DISTINCT primary_domain
        FROM word_domains
        WHERE primary_domain IS NOT NULL
        ORDER BY 1
        """

        try:
            with db_manager.get_cursor() as cursor:
                cursor.execute(sql)
                results = cursor.fetchall()
            return [row[0] for row in results if row[0]]
        except pg_errors.UndefinedTable:
            logger.warning("word_domains table doesn't exist, returning empty list")
            return []
        except Exception as exc:
            logger.error(f"Error getting domains: {exc}")
            return []

    def get_parts_of_speech(self) -> List[str]:
        with db_manager.get_cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT part_of_speech FROM defined "
                "WHERE part_of_speech IS NOT NULL ORDER BY part_of_speech"
            )
            results = cursor.fetchall()
        return [row[0] for row in results if row[0]]

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
    
    count_query = f"SELECT COUNT(*) FROM ({base_query}) as filtered"
    letter_query = None
    letter_params: list[Any] = []

    with db_manager.get_cursor() as cursor:
        cursor.execute(count_query, params)
        total_words = cursor.fetchone()[0]

    available_letters: list[str] = []
    if total_words > 0:
        if not letters:
            letter_query = """
            SELECT DISTINCT LOWER(LEFT(d.term, 1)) as first_letter
            FROM defined d
            LEFT JOIN word_domains wd ON d.id = wd.word_id
            WHERE 1=1
            """
            if domain:
                letter_query += " AND wd.primary_domain = %s"
                letter_params.append(domain)
            if part_of_speech:
                letter_query += " AND d.part_of_speech = %s"
                letter_params.append(part_of_speech)
            letter_query += " ORDER BY first_letter"
        else:
            next_pos = len(letters) + 1
            letter_query = (
                "SELECT DISTINCT LOWER(LEFT(d.term, %s)) as next_letters "
                "FROM defined d "
                "LEFT JOIN word_domains wd ON d.id = wd.word_id "
                "WHERE LOWER(d.term) LIKE %s AND LENGTH(d.term) >= %s"
            )
            letter_params = [next_pos, f"{letters.lower()}%", next_pos]
            if domain:
                letter_query += " AND wd.primary_domain = %s"
                letter_params.append(domain)
            if part_of_speech:
                letter_query += " AND d.part_of_speech = %s"
                letter_params.append(part_of_speech)
            letter_query += " ORDER BY next_letters"

        with db_manager.get_cursor() as cursor:
            cursor.execute(letter_query, letter_params)
            raw_letters = [row[0] for row in cursor.fetchall()]

        if not letters:
            available_letters = raw_letters
        else:
            available_letters = sorted({val[len(letters)] for val in raw_letters if len(val) > len(letters)})

    offset = (page - 1) * per_page
    words_query = f"{base_query} ORDER BY LOWER(d.term) ASC LIMIT %s OFFSET %s"
    words_params = params + [per_page, offset]

    with db_manager.get_cursor() as cursor:
        cursor.execute(words_query, words_params)
        results = cursor.fetchall()

    words = [
        Word(
            id=row[0],
            term=row[1],
            definition=row[2],
            part_of_speech=row[3],
            frequency_rank=row[4],
            independent_frequency=row[5],
            rarity_percentile=row[6],
            primary_domain=row[7],
            wav_url=row[8],
            ipa_transcription=row[9],
            arpabet_transcription=row[10],
            syllable_count=row[11],
            stress_pattern=row[12],
            obsolete_or_archaic=row[13],
        )
        for row in results
    ]
    
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

@app.get("/lookup", response_class=HTMLResponse)
async def word_lookup_page(request: Request, current_user: Optional[User] = Depends(get_optional_current_user)):
    """Display word lookup page"""
    return templates.TemplateResponse("lookup.html", {
        "request": request,
        "current_user": current_user
    })

@app.post("/lookup", response_class=HTMLResponse) 
async def word_lookup_results(
    request: Request,
    term: str = Form(...),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """Look up word definitions using comprehensive lookup system"""
    if not term or not term.strip():
        return templates.TemplateResponse("lookup.html", {
            "request": request,
            "current_user": current_user,
            "error": "Please enter a word to look up"
        })
    
    try:
        async with ComprehensiveDefinitionLookup() as lookup_system:
            result = await lookup_system.lookup_term(term.strip())
            
        return templates.TemplateResponse("lookup.html", {
            "request": request, 
            "current_user": current_user,
            "term": term,
            "result": result,
            "has_results": bool(result.definitions_by_pos)
        })
        
    except Exception as e:
        logger.error(f"Error looking up word '{term}': {e}")
        return templates.TemplateResponse("lookup.html", {
            "request": request,
            "current_user": current_user,
            "term": term,
            "error": f"Error looking up word: {str(e)}"
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

# Analytics endpoint
@app.get("/analytics", response_class=HTMLResponse)
async def user_analytics(request: Request, current_user: User = Depends(get_current_active_user)):
    """User analytics dashboard showing comprehensive vocabulary progress"""
    try:
        # Get comprehensive analytics for the current user
        analytics_data = analytics.get_comprehensive_analytics(current_user.id)

        return templates.TemplateResponse("analytics.html", {
            "request": request,
            "current_user": current_user,
            "analytics": analytics_data,
            "title": f"{current_user.username}'s Vocabulary Analytics"
        })

    except Exception as e:
        logger.error(f"Error loading analytics for user {current_user.id}: {e}")
        return templates.TemplateResponse("analytics.html", {
            "request": request,
            "current_user": current_user,
            "analytics": {"error": True, "message": "Unable to load analytics data. Please try again later."},
            "title": "Analytics - Error"
        })

# Admin endpoints
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Admin dashboard"""
    current_user = await get_current_admin_user(request)

    try:
        with db_manager.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = TRUE")
            active_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            admin_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM defined")
            total_words = cursor.fetchone()[0]

            cursor.execute(
                "SELECT id, username, email, full_name, role, is_active, created_at, last_login_at "
                "FROM users ORDER BY created_at DESC LIMIT 10"
            )
            recent_users = [
                User(
                    id=row[0],
                    username=row[1],
                    email=row[2],
                    full_name=row[3],
                    role=row[4],
                    is_active=row[5],
                    created_at=row[6],
                    last_login_at=row[7],
                )
                for row in cursor.fetchall()
            ]

        stats = {
            "total_users": total_users,
            "active_users": active_users,
            "admin_users": admin_users,
            "total_words": total_words,
            "database_name": db.config.get("dbname") or db.config.get("database", ""),
        }

        return templates.TemplateResponse("admin_dashboard.html", {
            "request": request,
            "current_user": current_user,
            "stats": stats,
            "recent_users": recent_users,
            "current_time": datetime.now()
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading admin dashboard: {e}")
        raise HTTPException(status_code=500, detail="Failed to load admin dashboard")

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
async def quiz_home(request: Request, current_user: User = Depends(get_current_active_user)):
    """Quiz home page - requires login"""
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
                    topic_domain: Optional[str] = Form(None),
                    num_questions: int = Form(10),
                    current_user: User = Depends(get_current_active_user)):
    """Start a new quiz session - requires login"""
    
    # Create quiz session in tracking system
    try:
        session_config = {
            "num_questions": num_questions,
            "seed": int(time.time() * 1000000) + current_user.id
        }
        session_id = quiz_tracker.create_quiz_session(
            user_id=current_user.id,
            quiz_type=quiz_type,
            difficulty=difficulty,
            topic_domain=topic_domain if topic_domain and topic_domain != "all" else None,
            total_questions=num_questions,
            session_config=session_config
        )
    except Exception as e:
        logger.error(f"Failed to create quiz session: {e}")
        raise HTTPException(status_code=500, detail="Failed to create quiz session")

    # Seed random with current time + user ID for maximum randomness per session
    seed = session_config["seed"]
    random.seed(seed)
    
    # Get random words for quiz - ensure we have enough words for uniqueness
    # For matching questions with 4 words per question, we need 4*num_questions unique words minimum
    # Get many more words to ensure randomness and uniqueness
    required_words = max(num_questions * 20, 500)  # Much larger pool for randomness
    
    # Use topic_domain parameter and handle empty string as None
    domain = topic_domain if topic_domain and topic_domain != "all" and topic_domain.strip() != "" else None
    words = db.search_words(domain=domain, limit=required_words)
    if len(words) < num_questions * 4:  # Need at least 4 words per question
        # Fallback to all words if domain doesn't have enough
        words = db.search_words(limit=required_words)
    
    if len(words) < num_questions * 4:
        raise HTTPException(status_code=400, detail=f"Not enough words available. Need {num_questions * 4} words, found {len(words)}")
    
    # Shuffle the entire word pool for maximum randomness
    random.shuffle(words)
    
    # Track ALL words used across the entire quiz to ensure no repetition
    used_word_ids = set()
    questions = []
    
    # Generate questions ensuring NO word appears more than once in the entire quiz
    word_index = 0  # Track position in shuffled words array
    
    for i in range(num_questions):
        question_id = i + 1
        
        # Determine question type for this question
        if quiz_type == "mixed":
            actual_type = random.choice(["multiple_choice", "true_false", "matching"])
        elif quiz_type == "multiple_choice":
            actual_type = "multiple_choice" 
        elif quiz_type == "true_false":
            actual_type = "true_false"
        elif quiz_type == "matching":
            actual_type = "matching"
        else:
            actual_type = "multiple_choice"  # fallback
        
        # Get the main word for this question
        if word_index >= len(words):
            break  # No more words available
        
        word = words[word_index]
        used_word_ids.add(word.id)
        word_index += 1
        
        if actual_type == "true_false":
            # Create True/False question
            # 50% chance of correct definition, 50% chance of wrong definition
            if random.choice([True, False]):
                # Use correct definition
                question_text = f"True or False: '{word.term}' means '{word.definition}'"
                correct_answer = True
                explanation = f"TRUE: '{word.term}' does mean '{word.definition}'"
            else:
                # Use wrong definition from another unused word
                unused_words = [w for w in words if w.id not in used_word_ids and w.part_of_speech == word.part_of_speech]
                if unused_words:
                    wrong_word = random.choice(unused_words)
                    used_word_ids.add(wrong_word.id)  # Mark as used
                    question_text = f"True or False: '{word.term}' means '{wrong_word.definition}'"
                    correct_answer = False
                    explanation = f"FALSE: '{word.term}' actually means '{word.definition}', not '{wrong_word.definition}'"
                else:
                    # Fallback to multiple choice if no unused distractors
                    actual_type = "multiple_choice"
        
        if actual_type == "multiple_choice":
            # Create multiple choice question using only unused words
            unused_distractors = [w for w in words if w.id not in used_word_ids and w.part_of_speech == word.part_of_speech]

            # If not enough same-POS words, broaden search to all parts of speech
            if len(unused_distractors) < 3:
                unused_distractors = [w for w in words if w.id not in used_word_ids]

            # Ensure at least 3 distractors for a 4-option multiple choice question
            num_distractors = min(3, len(unused_distractors))
            if num_distractors < 2:
                # Fall back to true/false if insufficient distractors
                actual_type = "true_false"
                correct_answer = True
                wrong_word = random.choice([w for w in words if w.id != word.id and w.id not in used_word_ids]) if len(words) > 1 else None
                if wrong_word:
                    used_word_ids.add(wrong_word.id)
                    question_text = f"Does '{word.term}' mean '{wrong_word.definition}'?"
                    explanation = f"FALSE: '{word.term}' actually means '{word.definition}', not '{wrong_word.definition}'"
                else:
                    question_text = f"Does '{word.term}' mean '{word.definition}'?"
                    explanation = f"TRUE: '{word.term}' means '{word.definition}'"
            else:
                selected_distractors = random.sample(unused_distractors, num_distractors)
                distractor_definitions = [d.definition for d in selected_distractors]

                # Mark distractor words as used
                for d in selected_distractors:
                    used_word_ids.add(d.id)

                options = [word.definition] + distractor_definitions
                random.shuffle(options)
                correct_answer = options.index(word.definition)
                question_text = f"What is the definition of '{word.term}'?"
                explanation = f"'{word.term}' means: {word.definition}"
        
        elif actual_type == "matching":
            # Initialize variables to prevent undefined errors
            terms = []
            shuffled_definitions = []
            correct_matches = {}

            # Create matching question using only unused words
            # Get 3 additional unused words (total 4 words for matching)
            unused_words = [w for w in words if w.id not in used_word_ids and w.part_of_speech == word.part_of_speech]
            num_additional = min(3, len(unused_words))
            additional_words = random.sample(unused_words, num_additional) if unused_words else []
            matching_words = [word] + additional_words

            # Mark ALL matching words as used
            for w in additional_words:
                used_word_ids.add(w.id)

            # Only create matching question if we have enough words (at least 2)
            if len(matching_words) >= 2:
                # Create lists of terms and definitions
                terms = [w.term for w in matching_words]
                definitions = [w.definition for w in matching_words]

                # Shuffle definitions but keep track of correct matches
                shuffled_definitions = definitions.copy()
                random.shuffle(shuffled_definitions)

                # Create correct answer mapping (term index -> definition index in shuffled list)
                correct_matches = {}
                for i, word_obj in enumerate(matching_words):
                    correct_def_index = shuffled_definitions.index(word_obj.definition)
                    correct_matches[i] = correct_def_index

                question_text = "Match each word with its correct definition:"
                explanation = "Matching question created successfully"
            else:
                # Fall back to multiple choice if not enough words for matching
                # Fallback to multiple choice if not enough words for matching
                actual_type = "multiple_choice"
                # Generate distractors for fallback
                distractor_definitions = random.sample([w.definition for w in words if w.id != word.id], 3)
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
        elif actual_type == "matching":
            question_data["terms"] = terms
            question_data["definitions"] = shuffled_definitions
            question_data["correct_matches"] = correct_matches
            # Pre-serialize JSON to avoid template issues with special characters
            import json
            import re

            # Clean Unicode characters that might cause issues
            def clean_unicode(text):
                if isinstance(text, str):
                    # Replace problematic Unicode characters with safe alternatives
                    text = re.sub(r'[\u2013\u2014]', '-', text)  # em/en dashes
                    text = re.sub(r'[\u2018\u2019]', "'", text)  # smart quotes
                    text = re.sub(r'[\u201c\u201d]', '"', text)  # smart quotes
                    text = re.sub(r'[\u2026]', '...', text)     # ellipsis
                    text = re.sub(r'[\u00a0]', ' ', text)       # non-breaking space
                    # Replace any remaining non-ASCII characters that might cause issues
                    text = re.sub(r'[^\x00-\x7F]+', '?', text)
                return text

            # Clean terms and definitions
            clean_terms = [clean_unicode(term) for term in terms]
            clean_definitions = [clean_unicode(definition) for definition in shuffled_definitions]

            # Always ensure JSON fields have valid values - never None or empty
            try:
                if clean_terms and clean_definitions:
                    question_data["terms_json"] = json.dumps(clean_terms, ensure_ascii=True)
                    question_data["definitions_json"] = json.dumps(clean_definitions, ensure_ascii=True)
                    question_data["correct_matches_json"] = json.dumps(correct_matches)
                else:
                    # Use test data if real data is empty
                    raise ValueError("Empty terms or definitions")
            except Exception as e:
                # Always provide valid JSON fallback
                test_terms = [f"TestTerm{i+1}" for i in range(4)]
                test_definitions = [f"Definition for test term {i+1}" for i in range(4)]
                test_matches = {0: 0, 1: 1, 2: 2, 3: 3}
                question_data["terms_json"] = json.dumps(test_terms, ensure_ascii=True)
                question_data["definitions_json"] = json.dumps(test_definitions, ensure_ascii=True)
                question_data["correct_matches_json"] = json.dumps(test_matches)
        else:  # true_false
            question_data["correct_answer"] = correct_answer
            
        questions.append(question_data)
    
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
                     results: str = Form(...),
                     current_user: User = Depends(get_current_active_user)):
    """Handle quiz submission and show results - requires login"""
    
    try:
        # Parse the results JSON
        import json
        results_data = json.loads(results)
        
        # Extract quiz information
        total_questions = results_data.get('totalQuestions', 0)
        correct_count = results_data.get('correctCount', 0)
        score = results_data.get('score', 0)
        difficulty = results_data.get('difficulty', 'medium')
        quiz_type = results_data.get('quizType', 'mixed')
        question_results = results_data.get('questions', [])
        review_data = results_data.get('reviewData', [])
        
        # Calculate accuracy percentage
        accuracy = round((correct_count / total_questions * 100) if total_questions > 0 else 0, 1)

        # Process review data for display
        correct_words = []
        incorrect_words = []

        for term_data in review_data:
            if term_data.get('is_correct', False):
                correct_words.append(term_data)
            else:
                incorrect_words.append(term_data)
        
        # If user is logged in, save quiz results using tracking system
        if current_user:
            try:
                # Record individual question results and update word mastery
                for question in question_results:
                    # Handle both old format (for backward compatibility) and new format
                    word_id = question.get('word_id') or question.get('wordId')
                    is_correct = question.get('is_correct', False)
                    response_time = question.get('response_time_ms') or question.get('responseTime', 0)

                    if word_id:
                        # Determine question type and difficulty based on quiz settings
                        if quiz_type == "multiple_choice":
                            question_type = QuestionType.MULTIPLE_CHOICE
                        elif quiz_type == "true_false":
                            question_type = QuestionType.TRUE_FALSE
                        elif quiz_type == "matching":
                            question_type = QuestionType.MATCHING
                        else:
                            question_type = QuestionType.MULTIPLE_CHOICE  # default

                        if difficulty == "easy":
                            difficulty_level = DifficultyLevel.EASY
                        elif difficulty == "hard":
                            difficulty_level = DifficultyLevel.HARD
                        else:
                            difficulty_level = DifficultyLevel.MEDIUM  # default

                        # Record question result and update word mastery
                        quiz_tracker.record_question_result(
                            user_id=current_user.id,
                            word_id=word_id,
                            session_id=session_id,
                            question_type=question_type,
                            is_correct=is_correct,
                            response_time_ms=response_time,
                            difficulty_level=difficulty_level
                        )

                # Complete the quiz session with final score
                quiz_tracker.complete_quiz_session(session_id, correct_count)

            except Exception as e:
                logger.warning(f"Failed to save quiz results using tracking system: {e}")
                # Continue anyway - don't fail the results display
        
        return templates.TemplateResponse("quiz_results.html", {
            "request": request,
            "current_user": current_user,
            "session_id": session_id,
            "total_questions": total_questions,
            "correct_count": correct_count,
            "accuracy": accuracy,
            "score": score,
            "difficulty": difficulty,
            "quiz_type": quiz_type,
            "question_results": question_results,
            "correct_words": correct_words,
            "incorrect_words": incorrect_words,
            "review_data": review_data
        })
        
    except Exception as e:
        logger.error(f"Error processing quiz results: {e}")
        raise HTTPException(status_code=500, detail="Failed to process quiz results")

# ==========================================
# HTMX QUIZ ENDPOINTS - MODERN IMPLEMENTATION
# ==========================================

@app.post("/quiz/matching/assign")
async def assign_matching_answer(
    request: Request,
    term_id: str = Form(...),
    definition_id: str = Form(...),
    question_id: str = Form(...),
    current_user: User = Depends(get_current_active_user)
):
    """HTMX endpoint to assign a definition to a term in matching quiz"""
    try:
        # This is a partial update - just return success/failure status
        # The client-side Alpine.js will handle the UI updates
        return JSONResponse({
            "success": True,
            "term_id": term_id,
            "definition_id": definition_id,
            "question_id": question_id
        })
    except Exception as e:
        logger.error(f"Error assigning matching answer: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@app.post("/quiz/matching/remove")
async def remove_matching_answer(
    request: Request,
    term_id: str = Form(...),
    question_id: str = Form(...),
    current_user: User = Depends(get_current_active_user)
):
    """HTMX endpoint to remove an assignment from a term in matching quiz"""
    try:
        return JSONResponse({
            "success": True,
            "term_id": term_id,
            "question_id": question_id
        })
    except Exception as e:
        logger.error(f"Error removing matching answer: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@app.post("/quiz/matching/validate")
async def validate_matching_question(
    request: Request,
    question_id: str = Form(...),
    assignments: str = Form(...),  # JSON string of assignments
    current_user: User = Depends(get_current_active_user)
):
    """HTMX endpoint to validate matching question answers"""
    try:
        import json
        assignments_data = json.loads(assignments)

        # Here you would validate against the correct answers
        # For now, return basic validation structure
        validation_results = {}

        for term_id, definition_id in assignments_data.items():
            # This is where you'd check if term_id matches definition_id correctly
            # For now, just return placeholder validation
            validation_results[term_id] = {
                "correct": True,  # Placeholder - implement actual validation
                "definition_id": definition_id
            }

        return JSONResponse({
            "success": True,
            "question_id": question_id,
            "results": validation_results
        })
    except Exception as e:
        logger.error(f"Error validating matching question: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

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

    def _cursor(self, autocommit: bool = False, dictionary: bool = False):
        return db_manager.get_cursor(autocommit=autocommit, dictionary=dictionary)

    def create_flashcard_tables(self):
        """Create flashcard tables if they don't exist (Postgres syntax)."""
        ddl_decks = """
        CREATE TABLE IF NOT EXISTS flashcard_decks (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """

        ddl_deck_items = """
        CREATE TABLE IF NOT EXISTS flashcard_deck_items (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            deck_id INTEGER NOT NULL,
            word_id INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (deck_id, word_id),
            FOREIGN KEY (deck_id) REFERENCES flashcard_decks(id) ON DELETE CASCADE,
            FOREIGN KEY (word_id) REFERENCES defined(id) ON DELETE CASCADE
        )
        """

        ddl_progress = """
        CREATE TABLE IF NOT EXISTS user_flashcard_progress (
            user_id INTEGER NOT NULL,
            word_id INTEGER NOT NULL,
            mastery_level TEXT DEFAULT 'learning',
            study_count INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            last_studied TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            next_review TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            interval_days INTEGER DEFAULT 1,
            ease_factor DOUBLE PRECISION DEFAULT 2.5,
            PRIMARY KEY (user_id, word_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (word_id) REFERENCES defined(id) ON DELETE CASCADE
        )
        """

        with self._cursor(autocommit=True) as cursor:
            cursor.execute(ddl_decks)
            cursor.execute(ddl_deck_items)
            cursor.execute(ddl_progress)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_flashcard_decks_user ON flashcard_decks (user_id)"
            )
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_flashcard_deck_items_unique ON flashcard_deck_items (deck_id, word_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_flashcard_next_review ON user_flashcard_progress (user_id, next_review)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_flashcard_mastery ON user_flashcard_progress (user_id, mastery_level)"
            )

        logger.info("Flashcard tables ensured in database")

    def get_user_decks(self, user_id: int) -> List[FlashcardDeck]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT fd.id, fd.name, fd.description, fd.user_id, fd.created_at,
                       COUNT(fdi.word_id) as word_count,
                       COALESCE(AVG(CASE
                           WHEN ufp.mastery_level = 'mastered' THEN 100
                           WHEN ufp.mastery_level = 'reviewing' THEN 60
                           ELSE 20
                       END), 0) as progress
                FROM flashcard_decks fd
                LEFT JOIN flashcard_deck_items fdi ON fd.id = fdi.deck_id
                LEFT JOIN user_flashcard_progress ufp
                    ON fdi.word_id = ufp.word_id AND ufp.user_id = %s
                WHERE fd.user_id = %s
                GROUP BY fd.id, fd.name, fd.description, fd.user_id, fd.created_at
                ORDER BY fd.created_at DESC
                """,
                (user_id, user_id),
            )
            decks = []
            for row in cursor.fetchall():
                decks.append(
                    FlashcardDeck(
                        id=row[0],
                        name=row[1],
                        description=row[2],
                        user_id=row[3],
                        created_at=row[4].isoformat() if row[4] else "",
                        word_count=row[5],
                        study_progress=float(row[6]),
                    )
                )
            return decks

    def create_deck(self, user_id: int, name: str, description: str = "") -> int:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO flashcard_decks (name, description, user_id)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (name, description, user_id),
            )
            deck_id = cursor.fetchone()[0]
            return deck_id

    def get_user_deck(self, deck_id: int, user_id: int) -> Optional[FlashcardDeck]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT d.id, d.name, d.description, d.user_id, d.created_at,
                       COUNT(fdi.id) as word_count
                FROM flashcard_decks d
                LEFT JOIN flashcard_deck_items fdi ON d.id = fdi.deck_id
                WHERE d.id = %s AND d.user_id = %s
                GROUP BY d.id, d.name, d.description, d.user_id, d.created_at
                """,
                (deck_id, user_id),
            )
            result = cursor.fetchone()
            if not result:
                return None
            return FlashcardDeck(
                id=result[0],
                name=result[1],
                description=result[2],
                user_id=result[3],
                created_at=result[4].isoformat() if result[4] else "",
                word_count=result[5],
            )

    def delete_deck(self, deck_id: int, user_id: int) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                "DELETE FROM flashcard_decks WHERE id = %s AND user_id = %s",
                (deck_id, user_id),
            )
            return cursor.rowcount > 0

    def add_word_to_deck(self, deck_id: int, word_id: int):
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO flashcard_deck_items (deck_id, word_id)
                VALUES (%s, %s)
                ON CONFLICT (deck_id, word_id) DO NOTHING
                """,
                (deck_id, word_id),
            )

    def remove_word_from_deck(self, deck_id: int, word_id: int):
        with self._cursor() as cursor:
            cursor.execute(
                "DELETE FROM flashcard_deck_items WHERE deck_id = %s AND word_id = %s",
                (deck_id, word_id),
            )

    def get_deck_cards(self, deck_id: int, user_id: int, limit: int = 200) -> List[Flashcard]:
        with self._cursor() as cursor:
            cursor.execute(
                """
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
                LEFT JOIN user_flashcard_progress ufp
                    ON d.id = ufp.word_id AND ufp.user_id = %s
                WHERE fdi.deck_id = %s AND fd.user_id = %s
                ORDER BY 
                    CASE COALESCE(ufp.mastery_level, 'learning')
                        WHEN 'learning' THEN 1 
                        WHEN 'reviewing' THEN 2 
                        WHEN 'mastered' THEN 3 
                        ELSE 0 
                    END,
                    COALESCE(ufp.next_review, NOW())
                LIMIT %s
                """,
                (user_id, deck_id, user_id, limit),
            )
            cards = []
            for row in cursor.fetchall():
                word = Word(
                    id=row[2],
                    term=row[3],
                    definition=row[4],
                    part_of_speech=row[5],
                    frequency=row[6],
                    frequency_rank=row[7],
                    independent_frequency=row[8],
                    rarity_percentile=row[9],
                    primary_domain=row[10],
                    wav_url=row[11],
                    ipa_transcription=row[12],
                    arpabet_transcription=row[13],
                    syllable_count=row[14],
                    stress_pattern=row[15],
                )
                cards.append(
                    Flashcard(
                        id=row[0],
                        word_id=row[0],
                        deck_id=row[1],
                        word=word,
                        mastery_level=row[16],
                        last_studied=row[17].isoformat() if row[17] else None,
                        study_count=row[18] or 0,
                        success_rate=float(row[19] or 0.0),
                    )
                )
            return cards

    def update_card_progress(self, user_id: int, word_id: int, is_correct: bool):
        correct_increment = 1 if is_correct else 0
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_flashcard_progress (
                    user_id, word_id, study_count, correct_count, last_studied, next_review, mastery_level, interval_days
                )
                VALUES (%s, %s, 1, %s, NOW(), NOW() + INTERVAL '1 day', 'learning', 1)
                ON CONFLICT (user_id, word_id) DO UPDATE SET
                    study_count = user_flashcard_progress.study_count + 1,
                    correct_count = user_flashcard_progress.correct_count + EXCLUDED.correct_count,
                    last_studied = NOW(),
                    mastery_level = CASE
                        WHEN (user_flashcard_progress.correct_count + EXCLUDED.correct_count) >= (user_flashcard_progress.study_count + 1) * 0.9
                             AND user_flashcard_progress.study_count + 1 >= 5 THEN 'mastered'
                        WHEN (user_flashcard_progress.correct_count + EXCLUDED.correct_count) >= (user_flashcard_progress.study_count + 1) * 0.8
                             AND user_flashcard_progress.study_count + 1 >= 3 THEN 'reviewing'
                        ELSE user_flashcard_progress.mastery_level
                    END,
                    next_review = CASE
                        WHEN EXCLUDED.correct_count > 0 THEN NOW() + INTERVAL '1 day' * LEAST(user_flashcard_progress.interval_days * 2, 30)
                        ELSE NOW() + INTERVAL '1 day'
                    END,
                    interval_days = CASE
                        WHEN EXCLUDED.correct_count > 0 THEN LEAST(user_flashcard_progress.interval_days * 2, 30)
                        ELSE GREATEST(user_flashcard_progress.interval_days / 2, 1)
                    END
                """,
                (user_id, word_id, correct_increment),
            )

    def get_random_cards(self, user_id: int, limit: int = 20) -> List[Flashcard]:
        with self._cursor() as cursor:
            cursor.execute(
                """
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
                WHERE d.definition IS NOT NULL AND d.definition <> ''
                ORDER BY RANDOM()
                LIMIT %s
                """,
                (user_id, limit),
            )
            cards = []
            for row in cursor.fetchall():
                word = Word(
                    id=row[2],
                    term=row[3],
                    definition=row[4],
                    part_of_speech=row[5],
                    frequency=row[6],
                    frequency_rank=row[7],
                    independent_frequency=row[8],
                    rarity_percentile=row[9],
                    primary_domain=row[10],
                    wav_url=row[11],
                    ipa_transcription=row[12],
                    arpabet_transcription=row[13],
                    syllable_count=row[14],
                    stress_pattern=row[15],
                )
                cards.append(
                    Flashcard(
                        id=row[0],
                        word_id=row[0],
                        deck_id=row[1],
                        word=word,
                        mastery_level=row[16],
                        last_studied=row[17].isoformat() if row[17] else None,
                        study_count=row[18] or 0,
                        success_rate=float(row[19] or 0.0),
                    )
                )
            return cards

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

@app.get("/api/word/{word_id}/definition")
async def get_word_definition(word_id: int):
    """Get definition for a word by ID"""
    try:
        with database_cursor() as cursor:
            cursor.execute("""
                SELECT term, definition, part_of_speech
                FROM defined
                WHERE id = %s
            """, (word_id,))

            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Word not found")

            return {
                "word_id": word_id,
                "term": result[0],
                "definition": result[1],
                "part_of_speech": result[2]
            }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting word definition: {e}")
        raise HTTPException(status_code=500, detail="Failed to get definition")

@app.get("/flashcards/guest/random", response_class=HTMLResponse)
async def guest_random_flashcards(request: Request, limit: int = 20):
    """Guest access to random flashcards for testing"""
    try:
        with db_manager.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, term, definition, part_of_speech, frequency
                FROM defined
                ORDER BY RANDOM()
                LIMIT %s
                """,
                (limit,),
            )
            results = cursor.fetchall()
        
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

# Admin Candidate Review Routes
@app.get("/admin/candidates", response_class=HTMLResponse)
async def admin_list_candidates(request: Request, 
                          status: str = Query("pending", description="Filter by status"),
                          page: int = Query(1, ge=1, description="Page number"),
                          per_page: int = Query(20, ge=1, le=100, description="Items per page"),
                          current_user: User = Depends(get_current_admin_user)):
    """List candidate words for review"""
    try:
        with db_manager.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM candidate_words WHERE review_status = %s", (status,))
            total_count = cursor.fetchone()[0]

            total_pages = (total_count + per_page - 1) // per_page
            offset = (page - 1) * per_page

            cursor.execute("""
                SELECT id, term, source_type, part_of_speech, utility_score,
                       rarity_indicators, context_snippet, raw_definition,
                       etymology_preview, date_discovered, review_status,
                       EXTRACT(DAY FROM (CURRENT_DATE - date_discovered)) AS days_pending
                FROM candidate_words
                WHERE review_status = %s
                ORDER BY utility_score DESC, date_discovered ASC
                LIMIT %s OFFSET %s
                """, (status, per_page, offset))
            candidates = [
                {
                    'id': row[0],
                    'term': row[1],
                    'source_type': row[2],
                    'part_of_speech': row[3],
                    'utility_score': float(row[4]) if row[4] else 0.0,
                    'rarity_indicators': row[5],
                    'context_snippet': row[6],
                    'raw_definition': row[7],
                    'etymology_preview': row[8],
                    'date_discovered': row[9],
                    'review_status': row[10],
                    'days_pending': int(row[11] or 0),
                }
                for row in cursor.fetchall()
            ]

            cursor.execute("""
                SELECT review_status, COUNT(*)
                FROM candidate_words
                GROUP BY review_status
                """)
            status_counts = {row[0]: row[1] for row in cursor.fetchall()}

        return templates.TemplateResponse("candidates.html", {
            "request": request,
            "current_user": current_user,
            "candidates": candidates,
            "status": status,
            "page": page,
            "per_page": per_page,
            "total_count": total_count,
            "total_pages": total_pages,
            "stats": status_counts,
        })
    except Exception as e:
        logger.error(f"Error loading candidates: {e}")
        raise HTTPException(status_code=500, detail="Failed to load candidates")


@app.get("/admin/candidates/{candidate_id}", response_class=HTMLResponse)
async def admin_view_candidate(request: Request, candidate_id: int,
                        current_user: User = Depends(get_current_admin_user)):
    """View detailed candidate information"""
    try:
        with db_manager.get_cursor(dictionary=True) as cursor:
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

        candidate = dict(row)

        return templates.TemplateResponse("candidate_detail.html", {
            "request": request,
            "current_user": current_user,
            "candidate": candidate,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading candidate: {e}")
        raise HTTPException(status_code=500, detail="Failed to load candidate")


@app.post("/admin/candidates/{candidate_id}/review")
async def admin_review_candidate(candidate_id: int,
                          action: str = Form(...),
                          reason: str = Form(None),
                          notes: str = Form(None),
                          current_user: User = Depends(get_current_admin_user)):
    """Review a candidate (approve, reject, or needs_info)"""
    valid_actions = {"approved", "rejected", "needs_info"}
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail="Invalid action")

    try:
        with db_manager.get_cursor(autocommit=True) as cursor:
            cursor.execute("""
                UPDATE candidate_words
                SET review_status = %s, rejection_reason = %s, notes = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (action, reason, notes, candidate_id))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Candidate not found")

        return RedirectResponse(url="/candidates", status_code=303)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reviewing candidate: {e}")
        raise HTTPException(status_code=500, detail="Failed to review candidate")



@app.get("/admin/definitions", response_class=HTMLResponse)
async def admin_definitions_editor(
    request: Request,
    search: Optional[str] = Query(None),
    part_of_speech: Optional[str] = Query(None),
    flag_filter: Optional[str] = Query(None),  # Keep for backward compatibility
    filter_circular: Optional[str] = Query(None),
    filter_bad: Optional[str] = Query(None),
    filter_review: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_admin_user)
):
    """Admin definition editing interface"""
    try:
        offset = (page - 1) * per_page
        
        result = definition_db.get_definitions_filtered(
            search=search,
            part_of_speech=part_of_speech,
            flag_filter=flag_filter,
            filter_circular=filter_circular,
            filter_bad=filter_bad,
            filter_review=filter_review,
            limit=per_page,
            offset=offset
        )
        
        definitions = result['definitions']
        total_count = result['total_count']
        
        # Calculate pagination
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
        
        # Generate page numbers for pagination
        start_page = max(1, page - 2)
        end_page = min(total_pages, page + 2)
        page_numbers = list(range(start_page, end_page + 1))
        
        # Get parts of speech for filter dropdown
        parts_of_speech = db.get_parts_of_speech()
        
        return templates.TemplateResponse("admin_definitions.html", {
            "request": request,
            "current_user": current_user,
            "definitions": definitions,
            "parts_of_speech": parts_of_speech,
            "search": search,
            "part_of_speech": part_of_speech,
            "flag_filter": flag_filter,
            "filter_circular": filter_circular,
            "filter_bad": filter_bad,
            "filter_review": filter_review,
            "current_page": page,
            "per_page": per_page,
            "total_count": total_count,
            "total_pages": total_pages,
            "page_numbers": page_numbers,
            "circular_count": result['circular_count'],
            "manual_review_count": result['manual_review_count'],
            "bad_count": result['bad_count']
        })
        
    except Exception as e:
        logger.error(f"Error loading admin definitions: {e}")
        raise HTTPException(status_code=500, detail="Failed to load definitions")

@app.post("/admin/definitions/bulk-update")
async def bulk_update_definitions(
    request: Request,
    current_user: User = Depends(get_current_admin_user)
):
    """Bulk update multiple definitions"""
    try:
        data = await request.json()
        changes = data.get('changes', [])
        
        if not changes:
            raise HTTPException(status_code=400, detail="No changes provided")
        
        definition_db.bulk_update_definitions(changes)
        
        return {"success": True, "message": f"Updated {len(changes)} definitions"}
        
    except Exception as e:
        logger.error(f"Error bulk updating definitions: {e}")
        raise HTTPException(status_code=500, detail="Failed to update definitions")

@app.delete("/admin/definitions/{definition_id}")
async def delete_definition(
    definition_id: int,
    current_user: User = Depends(get_current_admin_user)
):
    """Delete a single definition"""
    try:
        success = definition_db.delete_definition(definition_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Definition not found")
        
        return {"success": True, "message": "Definition deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting definition: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete definition")

@app.post("/admin/definitions/bulk-delete")
async def bulk_delete_definitions(
    request: Request,
    current_user: User = Depends(get_current_admin_user)
):
    """Bulk delete multiple definitions"""
    try:
        data = await request.json()
        ids = data.get('ids', [])
        
        if not ids:
            raise HTTPException(status_code=400, detail="No IDs provided")
        
        # Convert to integers
        definition_ids = [int(id) for id in ids]
        deleted_count = definition_db.bulk_delete_definitions(definition_ids)
        
        return {"success": True, "message": f"Deleted {deleted_count} definitions"}
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    except Exception as e:
        logger.error(f"Error bulk deleting definitions: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete definitions")

@app.put("/admin/definitions/{definition_id}")
async def update_definition(
    definition_id: int,
    request: Request,
    current_user: User = Depends(get_current_admin_user)
):
    """Update a single definition"""
    try:
        data = await request.json()
        
        # Validate and prepare update data
        update_data = {}
        allowed_fields = ['term', 'part_of_speech', 'definition', 'bad', 'has_circular_definition', 'needs_manual_circularity_review']
        
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No valid fields to update")
        
        success = definition_db.update_definition(definition_id, **update_data)
        
        if not success:
            raise HTTPException(status_code=404, detail="Definition not found")
        
        return {"success": True, "message": "Definition updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating definition: {e}")
        raise HTTPException(status_code=500, detail="Failed to update definition")

# Initialize flashcard tables on startup
try:
    flashcard_db.create_flashcard_tables()
except Exception as e:
    logger.warning(f"Could not create flashcard tables: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
