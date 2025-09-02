#!/usr/bin/env python3
"""
Simple FastAPI Vocabulary Web Application
Browse and explore vocabulary database - simplified working version
"""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List
import mysql.connector
from config import get_db_config
import random
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Vocabulary Explorer", description="Browse and explore vocabulary database")

# Setup templates
templates = Jinja2Templates(directory="templates")

class VocabularyDatabase:
    def __init__(self):
        self.config = get_db_config()
    
    def get_connection(self):
        return mysql.connector.connect(**self.config)
    
    def search_words(self, query: Optional[str] = None, limit: int = 50, offset: int = 0):
        """Simple word search - consolidated by word term"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if query:
            sql = """
            SELECT d.term, 
                   GROUP_CONCAT(DISTINCT d.definition SEPARATOR '; ') as definitions,
                   GROUP_CONCAT(DISTINCT d.part_of_speech SEPARATOR ', ') as parts_of_speech,
                   AVG(d.frequency) as avg_frequency,
                   MIN(wfi.frequency_rank) as best_frequency_rank,
                   AVG(wfi.independent_frequency) as avg_independent_frequency,
                   AVG(wfi.rarity_percentile) as avg_rarity_percentile,
                   wd.primary_domain,
                   MIN(d.id) as representative_id
            FROM defined d
            LEFT JOIN word_frequencies_independent wfi ON d.id = wfi.word_id
            LEFT JOIN word_domains wd ON d.id = wd.word_id
            WHERE d.term LIKE %s
            GROUP BY d.term, wd.primary_domain
            ORDER BY COALESCE(MIN(wfi.frequency_rank), 999999) ASC 
            LIMIT %s OFFSET %s
            """
            cursor.execute(sql, (f"%{query}%", limit, offset))
        else:
            sql = """
            SELECT d.term, 
                   GROUP_CONCAT(DISTINCT d.definition SEPARATOR '; ') as definitions,
                   GROUP_CONCAT(DISTINCT d.part_of_speech SEPARATOR ', ') as parts_of_speech,
                   AVG(d.frequency) as avg_frequency,
                   MIN(wfi.frequency_rank) as best_frequency_rank,
                   AVG(wfi.independent_frequency) as avg_independent_frequency,
                   AVG(wfi.rarity_percentile) as avg_rarity_percentile,
                   wd.primary_domain,
                   MIN(d.id) as representative_id
            FROM defined d
            LEFT JOIN word_frequencies_independent wfi ON d.id = wfi.word_id
            LEFT JOIN word_domains wd ON d.id = wd.word_id
            GROUP BY d.term, wd.primary_domain
            ORDER BY COALESCE(MIN(wfi.frequency_rank), 999999) ASC 
            LIMIT %s OFFSET %s
            """
            cursor.execute(sql, (limit, offset))
        
        results = cursor.fetchall()
        
        words = []
        for row in results:
            words.append({
                "id": row[8],  # representative_id
                "term": row[0],
                "definition": row[1],  # combined definitions
                "part_of_speech": row[2],  # combined parts of speech
                "frequency": row[3],
                "frequency_rank": row[4],
                "independent_frequency": row[5],
                "rarity_percentile": row[6],
                "primary_domain": row[7]
            })
        
        cursor.close()
        conn.close()
        return words
    
    def get_word_by_id(self, word_id: int):
        """Get word by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        sql = """
        SELECT d.id, d.term, d.definition, d.part_of_speech, d.frequency,
               wfi.frequency_rank, wfi.independent_frequency, wfi.rarity_percentile,
               wd.primary_domain
        FROM defined d
        LEFT JOIN word_frequencies_independent wfi ON d.id = wfi.word_id
        LEFT JOIN word_domains wd ON d.id = wd.word_id
        WHERE d.id = %s
        """
        
        cursor.execute(sql, (word_id,))
        result = cursor.fetchone()
        
        if not result:
            cursor.close()
            conn.close()
            return None
        
        word = {
            "id": result[0],
            "term": result[1],
            "definition": result[2],
            "part_of_speech": result[3],
            "frequency": result[4],
            "frequency_rank": result[5],
            "independent_frequency": result[6],
            "rarity_percentile": result[7],
            "primary_domain": result[8]
        }
        
        cursor.close()
        conn.close()
        return word
    
    def get_random_word(self):
        """Get a random word"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM defined")
        total_count = cursor.fetchone()[0]
        
        # Get random word
        random_offset = random.randint(0, total_count - 1)
        
        sql = """
        SELECT d.id, d.term, d.definition, d.part_of_speech, d.frequency,
               wfi.frequency_rank, wfi.independent_frequency, wfi.rarity_percentile,
               wd.primary_domain
        FROM defined d
        LEFT JOIN word_frequencies_independent wfi ON d.id = wfi.word_id
        LEFT JOIN word_domains wd ON d.id = wd.word_id
        LIMIT 1 OFFSET %s
        """
        
        cursor.execute(sql, (random_offset,))
        result = cursor.fetchone()
        
        word = {
            "id": result[0],
            "term": result[1],
            "definition": result[2],
            "part_of_speech": result[3],
            "frequency": result[4],
            "frequency_rank": result[5],
            "independent_frequency": result[6],
            "rarity_percentile": result[7],
            "primary_domain": result[8]
        }
        
        cursor.close()
        conn.close()
        return word
    
    def get_flashcard_set(self, domain: Optional[str] = None, min_freq: Optional[int] = None, 
                         max_freq: Optional[int] = None, limit: int = 20):
        """Get a set of words for flashcards"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        sql = """
        SELECT d.id, d.term, d.definition, d.part_of_speech, d.frequency,
               wfi.frequency_rank, wfi.independent_frequency, wfi.rarity_percentile,
               wd.primary_domain
        FROM defined d
        LEFT JOIN word_frequencies_independent wfi ON d.id = wfi.word_id
        LEFT JOIN word_domains wd ON d.id = wd.word_id
        WHERE 1=1
        """
        params = []
        
        if domain:
            sql += " AND wd.primary_domain = %s"
            params.append(domain)
        
        if min_freq:
            sql += " AND wfi.frequency_rank >= %s"
            params.append(min_freq)
        
        if max_freq:
            sql += " AND wfi.frequency_rank <= %s"
            params.append(max_freq)
        
        # Randomize the order for flashcards
        sql += " ORDER BY RAND() LIMIT %s"
        params.append(limit)
        
        cursor.execute(sql, params)
        results = cursor.fetchall()
        
        words = []
        for row in results:
            words.append({
                "id": row[0],
                "term": row[1],
                "definition": row[2],
                "part_of_speech": row[3],
                "frequency": row[4],
                "frequency_rank": row[5],
                "independent_frequency": row[6],
                "rarity_percentile": row[7],
                "primary_domain": row[8]
            })
        
        cursor.close()
        conn.close()
        return words
    
    def get_available_domains(self):
        """Get list of available domains for flashcard filtering"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        sql = """
        SELECT DISTINCT primary_domain 
        FROM word_domains 
        WHERE primary_domain IS NOT NULL 
        ORDER BY primary_domain
        """
        
        cursor.execute(sql)
        results = cursor.fetchall()
        domains = [row[0] for row in results if row[0]]
        
        cursor.close()
        conn.close()
        return domains
    
    def browse_words_enhanced(self, letter: Optional[str] = None, domain: Optional[str] = None, 
                            part_of_speech: Optional[str] = None, sort_by: str = "alphabetical", 
                            limit: int = 100, offset: int = 0):
        """Enhanced browse with filtering and sorting"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        sql = """
        SELECT d.id, d.term, d.definition, d.part_of_speech, d.frequency,
               wfi.frequency_rank, wfi.independent_frequency, wfi.rarity_percentile,
               wd.primary_domain
        FROM defined d
        LEFT JOIN word_frequencies_independent wfi ON d.id = wfi.word_id
        LEFT JOIN word_domains wd ON d.id = wd.word_id
        WHERE 1=1
        """
        params = []
        
        # Filter by starting letter
        if letter and len(letter) == 1:
            sql += " AND d.term LIKE %s"
            params.append(f"{letter}%")
        
        # Filter by domain
        if domain:
            sql += " AND wd.primary_domain = %s"
            params.append(domain)
        
        # Filter by part of speech
        if part_of_speech:
            sql += " AND d.part_of_speech = %s"
            params.append(part_of_speech)
        
        # Add sorting
        if sort_by == "rarity_asc":
            sql += " ORDER BY wfi.frequency_rank ASC, d.term ASC"
        elif sort_by == "rarity_desc":
            sql += " ORDER BY wfi.frequency_rank DESC, d.term ASC"
        elif sort_by == "frequency_desc":
            sql += " ORDER BY wfi.independent_frequency DESC, d.term ASC"
        else:  # alphabetical (default)
            sql += " ORDER BY d.term ASC"
        
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(sql, params)
        results = cursor.fetchall()
        
        words = []
        for row in results:
            words.append({
                "id": row[0],
                "term": row[1],
                "definition": row[2],
                "part_of_speech": row[3],
                "frequency": row[4],
                "frequency_rank": row[5],
                "independent_frequency": row[6],
                "rarity_percentile": row[7],
                "primary_domain": row[8]
            })
        
        cursor.close()
        conn.close()
        return words
    
    def get_letter_counts(self):
        """Get count of words starting with each letter"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        sql = """
        SELECT UPPER(LEFT(term, 1)) as letter, COUNT(DISTINCT term) as word_count
        FROM defined 
        WHERE term REGEXP '^[A-Za-z]'
        GROUP BY UPPER(LEFT(term, 1))
        ORDER BY letter
        """
        
        cursor.execute(sql)
        results = cursor.fetchall()
        
        letter_counts = {}
        for letter, count in results:
            letter_counts[letter] = count
        
        cursor.close()
        conn.close()
        return letter_counts

# Initialize database
db = VocabularyDatabase()

# API Endpoints
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Simple home page"""
    return """
    <html>
        <head>
            <title>Vocabulary Explorer</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
            <div class="container mt-5">
                <h1 class="text-center mb-4">📚 Vocabulary Explorer</h1>
                <div class="row justify-content-center">
                    <div class="col-md-6">
                        <form action="/search" method="get" class="mb-4">
                            <div class="input-group">
                                <input type="text" name="q" class="form-control" placeholder="Search for a word..." required>
                                <button type="submit" class="btn btn-primary">Search</button>
                            </div>
                        </form>
                        <div class="text-center">
                            <a href="/random" class="btn btn-outline-secondary">🎲 Random Word</a>
                            <a href="/browse" class="btn btn-outline-info">Browse All</a>
                            <a href="/flashcards" class="btn btn-success">📚 Flashcards</a>
                        </div>
                    </div>
                </div>
            </div>
        </body>
    </html>
    """

@app.get("/api/words")
async def search_words(
    q: Optional[str] = Query(None, description="Search query"),
    limit: int = Query(50, description="Number of results"),
    offset: int = Query(0, description="Offset for pagination")
):
    """Search words API"""
    try:
        words = db.search_words(q, limit, offset)
        return {"words": words, "total": len(words)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/words/{word_id}")
async def get_word(word_id: int):
    """Get word by ID API"""
    word = db.get_word_by_id(word_id)
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")
    return {"word": word}

@app.get("/api/random")
async def get_random_word():
    """Random word API"""
    word = db.get_random_word()
    if not word:
        raise HTTPException(status_code=404, detail="No words found")
    return {"word": word}

@app.get("/api/flashcards")
async def get_flashcards(
    domain: Optional[str] = Query(None, description="Filter by domain"),
    min_freq: Optional[int] = Query(None, description="Minimum frequency rank"),
    max_freq: Optional[int] = Query(None, description="Maximum frequency rank"),
    limit: int = Query(20, description="Number of cards")
):
    """Get flashcard set API"""
    try:
        words = db.get_flashcard_set(domain, min_freq, max_freq, limit)
        return {"flashcards": words, "total": len(words)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/domains")
async def get_domains():
    """Get available domains for filtering"""
    try:
        domains = db.get_available_domains()
        return {"domains": domains}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/browse")
async def browse_enhanced(
    letter: Optional[str] = Query(None, description="Filter by starting letter"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    part_of_speech: Optional[str] = Query(None, description="Filter by part of speech"),
    sort_by: str = Query("alphabetical", description="Sort order: alphabetical, rarity_asc, rarity_desc, frequency_desc"),
    limit: int = Query(100, description="Number of results"),
    offset: int = Query(0, description="Offset for pagination")
):
    """Enhanced browse API with filtering and sorting"""
    try:
        words = db.browse_words_enhanced(letter, domain, part_of_speech, sort_by, limit, offset)
        return {"words": words, "total": len(words)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/letter-counts")
async def get_letter_counts():
    """Get word counts by starting letter"""
    try:
        counts = db.get_letter_counts()
        return {"letter_counts": counts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str):
    """Search results page"""
    words = db.search_words(q, limit=20)
    
    html = f"""
    <html>
        <head>
            <title>Search: {q} - Vocabulary Explorer</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
            <div class="container mt-4">
                <div class="d-flex justify-content-between align-items-center mb-4">
                    <h2>Search Results for "{q}"</h2>
                    <a href="/" class="btn btn-outline-primary">← Back to Search</a>
                </div>
                
                <div class="row">
    """
    
    for word in words:
        freq_badge = f'<span class="badge bg-info">Rank: {word["frequency_rank"]:,}</span>' if word["frequency_rank"] else ''
        domain_badge = f'<span class="badge bg-success">{word["primary_domain"]}</span>' if word["primary_domain"] else ''
        
        html += f"""
                    <div class="col-md-6 col-lg-4 mb-3">
                        <div class="card h-100">
                            <div class="card-body">
                                <h5 class="card-title">
                                    <a href="/word/{word['id']}" class="text-decoration-none">{word['term']}</a>
                                </h5>
                                {f'<span class="badge bg-secondary mb-2">{word["part_of_speech"]}</span>' if word["part_of_speech"] else ''}
                                <p class="card-text">{word['definition'][:150]}{'...' if len(word['definition']) > 150 else ''}</p>
                                <div>
                                    {freq_badge}
                                    {domain_badge}
                                </div>
                            </div>
                        </div>
                    </div>
        """
    
    html += """
                </div>
            </div>
        </body>
    </html>
    """
    
    return html

@app.get("/word/{word_id}", response_class=HTMLResponse)
async def word_detail(request: Request, word_id: int):
    """Word detail page"""
    word = db.get_word_by_id(word_id)
    if not word:
        raise HTTPException(status_code=404, detail="Word not found")
    
    freq_info = ""
    if word["frequency_rank"]:
        freq_info = f"""
        <div class="mb-3">
            <h6 class="text-muted">Frequency Information</h6>
            <p><strong>Rank:</strong> {word["frequency_rank"]:,} out of 22,094 words</p>
            {f'<p><strong>Rarity:</strong> {word["rarity_percentile"]:.1f}% of words are rarer</p>' if word["rarity_percentile"] else ''}
        </div>
        """
    
    domain_info = ""
    if word["primary_domain"]:
        domain_info = f"""
        <div class="mb-3">
            <h6 class="text-muted">Domain</h6>
            <span class="badge bg-success">{word["primary_domain"]}</span>
        </div>
        """
    
    html = f"""
    <html>
        <head>
            <title>{word['term']} - Vocabulary Explorer</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
            <div class="container mt-4">
                <div class="row justify-content-center">
                    <div class="col-lg-8">
                        <div class="card">
                            <div class="card-body p-4">
                                <div class="d-flex justify-content-between align-items-start mb-3">
                                    <div>
                                        <h1 class="display-4">{word['term']}</h1>
                                        {f'<span class="badge bg-secondary fs-6">{word["part_of_speech"]}</span>' if word["part_of_speech"] else ''}
                                    </div>
                                </div>
                                
                                <div class="mb-4">
                                    <h5 class="text-muted mb-2">Definition</h5>
                                    <p class="lead">{word['definition']}</p>
                                </div>
                                
                                {freq_info}
                                {domain_info}
                                
                                <div class="text-center mt-4">
                                    <a href="/" class="btn btn-outline-primary me-2">← Back to Search</a>
                                    <a href="/random" class="btn btn-primary">🎲 Random Word</a>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </body>
    </html>
    """
    
    return html

@app.get("/random", response_class=HTMLResponse)
async def random_word_page(request: Request):
    """Random word page"""
    word = db.get_random_word()
    
    freq_info = ""
    if word["frequency_rank"]:
        freq_info = f"""
        <div class="alert alert-info">
            <strong>Frequency Rank:</strong> {word["frequency_rank"]:,} out of 22,094 words
            {f' | <strong>Rarity:</strong> {word["rarity_percentile"]:.1f}% of words are rarer' if word["rarity_percentile"] else ''}
        </div>
        """
    
    domain_info = ""
    if word["primary_domain"]:
        domain_info = f'<span class="badge bg-success mb-3">{word["primary_domain"]}</span>'
    
    html = f"""
    <html>
        <head>
            <title>Random Word: {word['term']} - Vocabulary Explorer</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
            <div class="container mt-4">
                <div class="alert alert-success text-center">
                    🎲 <strong>Random Discovery!</strong> Here's a word to explore.
                </div>
                
                <div class="row justify-content-center">
                    <div class="col-lg-8">
                        <div class="card">
                            <div class="card-body p-4">
                                <h1 class="display-4 text-center mb-3">{word['term']}</h1>
                                {f'<div class="text-center mb-3"><span class="badge bg-secondary fs-6">{word["part_of_speech"]}</span></div>' if word["part_of_speech"] else ''}
                                {domain_info}
                                
                                <div class="mb-4">
                                    <h5 class="text-muted mb-2">Definition</h5>
                                    <p class="lead">{word['definition']}</p>
                                </div>
                                
                                {freq_info}
                                
                                <div class="text-center mt-4">
                                    <a href="/random" class="btn btn-primary me-2">🎲 Another Random Word</a>
                                    <a href="/" class="btn btn-outline-secondary">← Back to Search</a>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </body>
    </html>
    """
    
    return html

@app.get("/browse", response_class=HTMLResponse)
async def browse_words_enhanced_page(request: Request):
    """Enhanced browse all words page"""
    domains = db.get_available_domains()
    parts_of_speech = []
    try:
        # Get parts of speech from the original method
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT part_of_speech FROM defined WHERE part_of_speech IS NOT NULL ORDER BY part_of_speech")
        parts_of_speech = [row[0] for row in cursor.fetchall() if row[0]]
        cursor.close()
        conn.close()
    except:
        pass
    
    letter_counts = db.get_letter_counts()
    
    html = f"""
    <html>
        <head>
            <title>Browse Words - Vocabulary Explorer</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                .letter-nav {{
                    background: #f8f9fa;
                    padding: 1rem;
                    border-radius: 8px;
                    margin-bottom: 2rem;
                }}
                .letter-link {{
                    display: inline-block;
                    padding: 0.5rem 0.75rem;
                    margin: 0.2rem;
                    border: 1px solid #dee2e6;
                    border-radius: 4px;
                    color: #495057;
                    text-decoration: none;
                    transition: all 0.2s;
                }}
                .letter-link:hover, .letter-link.active {{
                    background: #007bff;
                    color: white;
                    border-color: #007bff;
                }}
                .letter-link.disabled {{
                    color: #6c757d;
                    background: #e9ecef;
                    cursor: not-allowed;
                }}
                .filters-section {{
                    background: #ffffff;
                    border: 1px solid #dee2e6;
                    border-radius: 8px;
                    padding: 1.5rem;
                    margin-bottom: 2rem;
                }}
                .word-card {{
                    transition: transform 0.2s;
                }}
                .word-card:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                }}
                .rarity-indicator {{
                    width: 100%;
                    height: 4px;
                    background: #e9ecef;
                    border-radius: 2px;
                    overflow: hidden;
                }}
                .rarity-bar {{
                    height: 100%;
                    border-radius: 2px;
                }}
                .rarity-common {{ background: #28a745; }}
                .rarity-uncommon {{ background: #ffc107; }}
                .rarity-rare {{ background: #fd7e14; }}
                .rarity-very-rare {{ background: #dc3545; }}
                .rarity-ultra-rare {{ background: #6f42c1; }}
            </style>
        </head>
        <body>
            <div class="container-fluid mt-4">
                <div class="d-flex justify-content-between align-items-center mb-4">
                    <h2>📖 Browse All Words</h2>
                    <a href="/" class="btn btn-outline-primary">← Back to Home</a>
                </div>
                
                <!-- Alphabet Navigation -->
                <div class="letter-nav">
                    <h5 class="mb-3">Browse by Starting Letter:</h5>
                    <a href="#" class="letter-link" onclick="filterByLetter('')" id="letter-all">All</a>
                    {chr(10).join([
                        f'<a href="#" class="letter-link{" disabled" if letter not in letter_counts else ""}" '
                        f'onclick="filterByLetter(\'{letter}\')" id="letter-{letter}">'
                        f'{letter} ({letter_counts.get(letter, 0)})</a>'
                        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                    ])}
                </div>
                
                <!-- Filters and Sorting -->
                <div class="filters-section">
                    <div class="row">
                        <div class="col-md-3">
                            <label class="form-label">Domain Filter</label>
                            <select id="domain-filter" class="form-select">
                                <option value="">All Domains</option>
                                {chr(10).join([f'<option value="{domain}">{domain}</option>' for domain in domains[:15]])}
                            </select>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">Part of Speech</label>
                            <select id="pos-filter" class="form-select">
                                <option value="">All Parts of Speech</option>
                                {chr(10).join([f'<option value="{pos}">{pos}</option>' for pos in parts_of_speech[:10]])}
                            </select>
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">Sort By</label>
                            <select id="sort-by" class="form-select">
                                <option value="alphabetical">Alphabetical (A-Z)</option>
                                <option value="rarity_asc">Rarest First</option>
                                <option value="rarity_desc">Most Common First</option>
                                <option value="frequency_desc">Highest Frequency</option>
                            </select>
                        </div>
                        <div class="col-md-3 d-flex align-items-end">
                            <button class="btn btn-primary w-100" onclick="applyFilters()">Apply Filters</button>
                        </div>
                    </div>
                    
                    <div class="row mt-3">
                        <div class="col-md-12">
                            <div id="filter-status" class="text-muted small"></div>
                        </div>
                    </div>
                </div>
                
                <!-- Results Section -->
                <div id="results-section">
                    <div class="text-center text-muted py-5">
                        <h4>Select a letter or apply filters to browse words</h4>
                        <p>Use the alphabet navigation above or set filters to explore your vocabulary.</p>
                    </div>
                </div>
                
                <!-- Pagination -->
                <div id="pagination-section" class="d-flex justify-content-center mt-4" style="display: none;">
                    <nav>
                        <ul class="pagination" id="pagination">
                        </ul>
                    </nav>
                </div>
            </div>
            
            <script>
                let currentLetter = '';
                let currentPage = 0;
                let currentFilters = {{}};
                let totalResults = 0;
                const resultsPerPage = 50;
                
                function filterByLetter(letter) {{
                    // Update UI
                    document.querySelectorAll('.letter-link').forEach(link => link.classList.remove('active'));
                    if (letter) {{
                        document.getElementById(`letter-${{letter}}`).classList.add('active');
                    }} else {{
                        document.getElementById('letter-all').classList.add('active');
                    }}
                    
                    currentLetter = letter;
                    currentPage = 0;
                    loadWords();
                }}
                
                function applyFilters() {{
                    currentFilters = {{
                        domain: document.getElementById('domain-filter').value,
                        part_of_speech: document.getElementById('pos-filter').value,
                        sort_by: document.getElementById('sort-by').value
                    }};
                    currentPage = 0;
                    loadWords();
                }}
                
                async function loadWords() {{
                    const params = new URLSearchParams();
                    
                    if (currentLetter) params.append('letter', currentLetter);
                    if (currentFilters.domain) params.append('domain', currentFilters.domain);
                    if (currentFilters.part_of_speech) params.append('part_of_speech', currentFilters.part_of_speech);
                    if (currentFilters.sort_by) params.append('sort_by', currentFilters.sort_by);
                    
                    params.append('limit', resultsPerPage);
                    params.append('offset', currentPage * resultsPerPage);
                    
                    try {{
                        const response = await fetch(`/api/browse?${{params.toString()}}`);
                        const data = await response.json();
                        
                        displayResults(data.words);
                        updateFilterStatus(data.words.length);
                        
                    }} catch (error) {{
                        console.error('Error loading words:', error);
                        document.getElementById('results-section').innerHTML = `
                            <div class="alert alert-danger">
                                <h5>Error loading words</h5>
                                <p>Please try again or adjust your filters.</p>
                            </div>
                        `;
                    }}
                }}
                
                function displayResults(words) {{
                    if (words.length === 0) {{
                        document.getElementById('results-section').innerHTML = `
                            <div class="alert alert-info text-center">
                                <h5>No words found</h5>
                                <p>Try adjusting your filters or selecting a different letter.</p>
                            </div>
                        `;
                        return;
                    }}
                    
                    let html = `<div class="row">`;
                    
                    words.forEach(word => {{
                        const freqRank = word.frequency_rank ? `Rank: ${{word.frequency_rank.toLocaleString()}}` : 'Unranked';
                        const rarity = word.rarity_percentile || 0;
                        
                        let rarityClass = 'rarity-common';
                        let rarityLabel = 'Common';
                        if (rarity >= 95) {{ rarityClass = 'rarity-ultra-rare'; rarityLabel = 'Ultra Rare'; }}
                        else if (rarity >= 90) {{ rarityClass = 'rarity-very-rare'; rarityLabel = 'Very Rare'; }}
                        else if (rarity >= 75) {{ rarityClass = 'rarity-rare'; rarityLabel = 'Rare'; }}
                        else if (rarity >= 50) {{ rarityClass = 'rarity-uncommon'; rarityLabel = 'Uncommon'; }}
                        
                        html += `
                            <div class="col-md-6 col-lg-4 col-xl-3 mb-4">
                                <div class="card word-card h-100">
                                    <div class="card-body">
                                        <h5 class="card-title">
                                            <a href="/word/${{word.id}}" class="text-decoration-none">${{word.term}}</a>
                                        </h5>
                                        ${{word.part_of_speech ? `<span class="badge bg-secondary mb-2">${{word.part_of_speech}}</span>` : ''}}
                                        <p class="card-text small">${{word.definition.substring(0, 120)}}${{word.definition.length > 120 ? '...' : ''}}</p>
                                        
                                        <div class="mt-auto">
                                            <div class="rarity-indicator mb-2">
                                                <div class="rarity-bar ${{rarityClass}}" style="width: ${{rarity}}%"></div>
                                            </div>
                                            <div class="d-flex justify-content-between align-items-center">
                                                <small class="text-muted">${{rarityLabel}}</small>
                                                <small class="badge bg-info">${{freqRank}}</small>
                                            </div>
                                            ${{word.primary_domain ? `<small class="badge bg-success mt-1">${{word.primary_domain}}</small>` : ''}}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        `;
                    }});
                    
                    html += `</div>`;
                    document.getElementById('results-section').innerHTML = html;
                }}
                
                function updateFilterStatus(count) {{
                    let status = `Showing ${{count}} words`;
                    
                    const filters = [];
                    if (currentLetter) filters.push(`starting with "${{currentLetter}}"`);
                    if (currentFilters.domain) filters.push(`in domain "${{currentFilters.domain}}"`);
                    if (currentFilters.part_of_speech) filters.push(`part of speech "${{currentFilters.part_of_speech}}"`);
                    
                    if (filters.length > 0) {{
                        status += ` ${{filters.join(', ')}}`;
                    }}
                    
                    const sortLabel = {{
                        'alphabetical': 'sorted alphabetically',
                        'rarity_asc': 'sorted by rarity (rarest first)',
                        'rarity_desc': 'sorted by rarity (most common first)',
                        'frequency_desc': 'sorted by frequency (highest first)'
                    }};
                    
                    if (currentFilters.sort_by && currentFilters.sort_by !== 'alphabetical') {{
                        status += `, ${{sortLabel[currentFilters.sort_by] || 'custom sorted'}}`;
                    }}
                    
                    document.getElementById('filter-status').textContent = status;
                }}
                
                // Initialize
                document.addEventListener('DOMContentLoaded', function() {{
                    document.getElementById('letter-all').classList.add('active');
                }});
            </script>
        </body>
    </html>
    """
    
    return html

@app.get("/flashcards", response_class=HTMLResponse)
async def flashcards_page(request: Request):
    """Flashcards setup and practice page"""
    domains = db.get_available_domains()
    
    html = f"""
    <html>
        <head>
            <title>Flashcards - Vocabulary Explorer</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                .flashcard {{
                    width: 400px;
                    height: 250px;
                    perspective: 1000px;
                    margin: 0 auto;
                    cursor: pointer;
                }}
                
                .flashcard-inner {{
                    position: relative;
                    width: 100%;
                    height: 100%;
                    text-align: center;
                    transition: transform 0.6s;
                    transform-style: preserve-3d;
                }}
                
                .flashcard.flipped .flashcard-inner {{
                    transform: rotateY(180deg);
                }}
                
                .flashcard-front, .flashcard-back {{
                    position: absolute;
                    width: 100%;
                    height: 100%;
                    backface-visibility: hidden;
                    border-radius: 10px;
                    border: 2px solid #007bff;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    flex-direction: column;
                    padding: 20px;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                }}
                
                .flashcard-front {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }}
                
                .flashcard-back {{
                    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                    color: white;
                    transform: rotateY(180deg);
                }}
                
                .controls {{
                    margin-top: 2rem;
                    text-align: center;
                }}
                
                .progress-stats {{
                    background: #f8f9fa;
                    border-radius: 8px;
                    padding: 1rem;
                    margin: 1rem 0;
                }}
                
                .setup-section {{
                    background: #f8f9fa;
                    border-radius: 8px;
                    padding: 2rem;
                    margin-bottom: 2rem;
                }}
                
                #flashcard-container {{
                    display: none;
                }}
                
                .btn-correct {{
                    background: #28a745;
                    border-color: #28a745;
                    color: white;
                }}
                
                .btn-incorrect {{
                    background: #dc3545;
                    border-color: #dc3545;
                    color: white;
                }}
            </style>
        </head>
        <body>
            <div class="container mt-4">
                <div class="d-flex justify-content-between align-items-center mb-4">
                    <h2>📚 Flashcards</h2>
                    <a href="/" class="btn btn-outline-primary">← Back to Home</a>
                </div>
                
                <!-- Setup Section -->
                <div id="setup-section" class="setup-section">
                    <h4 class="mb-3">Create Your Flashcard Set</h4>
                    <div class="row">
                        <div class="col-md-4">
                            <label class="form-label">Domain (Optional)</label>
                            <select id="domain-filter" class="form-select">
                                <option value="">All Domains</option>
                                {chr(10).join([f'<option value="{domain}">{domain}</option>' for domain in domains[:20]])}
                            </select>
                        </div>
                        <div class="col-md-4">
                            <label class="form-label">Frequency Range</label>
                            <div class="input-group">
                                <input type="number" id="min-freq" class="form-control" placeholder="Min rank" min="1" max="22000">
                                <input type="number" id="max-freq" class="form-control" placeholder="Max rank" min="1" max="22000">
                            </div>
                            <small class="text-muted">Lower numbers = more common words</small>
                        </div>
                        <div class="col-md-4">
                            <label class="form-label">Number of Cards</label>
                            <select id="card-count" class="form-select">
                                <option value="10">10 cards</option>
                                <option value="20" selected>20 cards</option>
                                <option value="30">30 cards</option>
                                <option value="50">50 cards</option>
                            </select>
                        </div>
                    </div>
                    <div class="text-center mt-3">
                        <button id="start-flashcards" class="btn btn-primary btn-lg">Start Flashcards</button>
                    </div>
                </div>
                
                <!-- Flashcard Practice Section -->
                <div id="flashcard-container">
                    <div class="progress-stats">
                        <div class="row text-center">
                            <div class="col-md-3">
                                <h5 id="current-card">1</h5>
                                <small class="text-muted">Current Card</small>
                            </div>
                            <div class="col-md-3">
                                <h5 id="total-cards">20</h5>
                                <small class="text-muted">Total Cards</small>
                            </div>
                            <div class="col-md-3">
                                <h5 id="correct-count">0</h5>
                                <small class="text-muted">Correct</small>
                            </div>
                            <div class="col-md-3">
                                <h5 id="incorrect-count">0</h5>
                                <small class="text-muted">Incorrect</small>
                            </div>
                        </div>
                        <div class="progress mt-2">
                            <div id="progress-bar" class="progress-bar" role="progressbar" style="width: 5%"></div>
                        </div>
                    </div>
                    
                    <div class="flashcard" id="flashcard" onclick="flipCard()">
                        <div class="flashcard-inner">
                            <div class="flashcard-front">
                                <h2 id="card-word">Loading...</h2>
                                <p class="mt-3"><small>Click to reveal definition</small></p>
                            </div>
                            <div class="flashcard-back">
                                <p id="card-definition">Loading...</p>
                                <div class="mt-3">
                                    <span id="card-pos" class="badge bg-light text-dark"></span>
                                    <span id="card-domain" class="badge bg-success"></span>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="controls">
                        <button id="btn-incorrect" class="btn btn-incorrect me-3" onclick="markCard(false)">❌ Incorrect</button>
                        <button id="btn-correct" class="btn btn-correct" onclick="markCard(true)">✅ Correct</button>
                    </div>
                    
                    <div class="text-center mt-4">
                        <button id="btn-restart" class="btn btn-outline-secondary me-2" onclick="restartFlashcards()">🔄 New Set</button>
                        <button id="btn-flip" class="btn btn-outline-info" onclick="flipCard()">🔄 Flip Card</button>
                    </div>
                </div>
                
                <!-- Results Section -->
                <div id="results-section" style="display: none;">
                    <div class="card text-center">
                        <div class="card-body">
                            <h3 class="card-title">🎉 Flashcard Session Complete!</h3>
                            <div class="row mt-4">
                                <div class="col-md-6">
                                    <h4 id="final-correct" class="text-success">0</h4>
                                    <p class="text-muted">Correct Answers</p>
                                </div>
                                <div class="col-md-6">
                                    <h4 id="final-accuracy" class="text-info">0%</h4>
                                    <p class="text-muted">Accuracy</p>
                                </div>
                            </div>
                            <div class="mt-4">
                                <button class="btn btn-primary me-2" onclick="restartFlashcards()">📚 New Flashcard Set</button>
                                <a href="/" class="btn btn-outline-secondary">← Back to Home</a>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script>
                let flashcards = [];
                let currentCardIndex = 0;
                let correctCount = 0;
                let incorrectCount = 0;
                let isFlipped = false;
                
                // Keyboard shortcuts
                document.addEventListener('keydown', function(e) {{
                    if (document.getElementById('flashcard-container').style.display !== 'none') {{
                        switch(e.code) {{
                            case 'Space':
                                e.preventDefault();
                                flipCard();
                                break;
                            case 'ArrowLeft':
                                e.preventDefault();
                                markCard(false);
                                break;
                            case 'ArrowRight':
                                e.preventDefault();
                                markCard(true);
                                break;
                        }}
                    }}
                }});
                
                async function startFlashcards() {{
                    const domain = document.getElementById('domain-filter').value;
                    const minFreq = document.getElementById('min-freq').value;
                    const maxFreq = document.getElementById('max-freq').value;
                    const limit = document.getElementById('card-count').value;
                    
                    const params = new URLSearchParams();
                    if (domain) params.append('domain', domain);
                    if (minFreq) params.append('min_freq', minFreq);
                    if (maxFreq) params.append('max_freq', maxFreq);
                    params.append('limit', limit);
                    
                    try {{
                        const response = await fetch(`/api/flashcards?${{params.toString()}}`);
                        const data = await response.json();
                        
                        flashcards = data.flashcards;
                        if (flashcards.length === 0) {{
                            alert('No words found with the selected criteria. Try adjusting your filters.');
                            return;
                        }}
                        
                        currentCardIndex = 0;
                        correctCount = 0;
                        incorrectCount = 0;
                        
                        document.getElementById('setup-section').style.display = 'none';
                        document.getElementById('flashcard-container').style.display = 'block';
                        document.getElementById('results-section').style.display = 'none';
                        document.getElementById('total-cards').textContent = flashcards.length;
                        
                        showCard();
                    }} catch (error) {{
                        console.error('Error loading flashcards:', error);
                        alert('Error loading flashcards. Please try again.');
                    }}
                }}
                
                function showCard() {{
                    const card = flashcards[currentCardIndex];
                    const flashcardElement = document.getElementById('flashcard');
                    
                    // Reset flip state
                    flashcardElement.classList.remove('flipped');
                    isFlipped = false;
                    
                    // Update card content
                    document.getElementById('card-word').textContent = card.term;
                    document.getElementById('card-definition').textContent = card.definition;
                    document.getElementById('card-pos').textContent = card.part_of_speech || '';
                    document.getElementById('card-domain').textContent = card.primary_domain || '';
                    
                    // Update progress
                    document.getElementById('current-card').textContent = currentCardIndex + 1;
                    document.getElementById('correct-count').textContent = correctCount;
                    document.getElementById('incorrect-count').textContent = incorrectCount;
                    
                    const progress = ((currentCardIndex + 1) / flashcards.length) * 100;
                    document.getElementById('progress-bar').style.width = `${{progress}}%`;
                }}
                
                function flipCard() {{
                    const flashcardElement = document.getElementById('flashcard');
                    flashcardElement.classList.toggle('flipped');
                    isFlipped = !isFlipped;
                }}
                
                function markCard(isCorrect) {{
                    if (!isFlipped) {{
                        flipCard();
                        setTimeout(() => {{ actuallyMarkCard(isCorrect); }}, 600);
                    }} else {{
                        actuallyMarkCard(isCorrect);
                    }}
                }}
                
                function actuallyMarkCard(isCorrect) {{
                    if (isCorrect) {{
                        correctCount++;
                    }} else {{
                        incorrectCount++;
                    }}
                    
                    currentCardIndex++;
                    
                    if (currentCardIndex >= flashcards.length) {{
                        // Session complete
                        showResults();
                    }} else {{
                        setTimeout(() => {{ showCard(); }}, 300);
                    }}
                }}
                
                function showResults() {{
                    const accuracy = Math.round((correctCount / flashcards.length) * 100);
                    
                    document.getElementById('flashcard-container').style.display = 'none';
                    document.getElementById('results-section').style.display = 'block';
                    
                    document.getElementById('final-correct').textContent = `${{correctCount}}/${{flashcards.length}}`;
                    document.getElementById('final-accuracy').textContent = `${{accuracy}}%`;
                }}
                
                function restartFlashcards() {{
                    document.getElementById('setup-section').style.display = 'block';
                    document.getElementById('flashcard-container').style.display = 'none';
                    document.getElementById('results-section').style.display = 'none';
                }}
                
                // Event listeners
                document.getElementById('start-flashcards').addEventListener('click', startFlashcards);
            </script>
        </body>
    </html>
    """
    
    return html

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)