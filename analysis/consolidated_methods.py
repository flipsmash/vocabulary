#!/usr/bin/env python3
"""
Consolidated database methods for word-based operations
Treats each word as a unit, combining multiple POS entries
"""

def search_words_consolidated(self, query: Optional[str] = None, limit: int = 50, offset: int = 0):
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
        FROM vocab.defined d
        LEFT JOIN vocab.word_frequencies_independent wfi ON d.id = wfi.word_id
        LEFT JOIN vocab.word_domains wd ON d.id = wd.word_id
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
        FROM vocab.defined d
        LEFT JOIN vocab.word_frequencies_independent wfi ON d.id = wfi.word_id
        LEFT JOIN vocab.word_domains wd ON d.id = wd.word_id
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

def browse_words_enhanced_consolidated(self, letter: Optional[str] = None, domain: Optional[str] = None, 
                        part_of_speech: Optional[str] = None, sort_by: str = "alphabetical", 
                        limit: int = 100, offset: int = 0):
    """Enhanced browse with filtering and sorting - consolidated by word term"""
    conn = self.get_connection()
    cursor = conn.cursor()
    
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
    FROM vocab.defined d
    LEFT JOIN vocab.word_frequencies_independent wfi ON d.id = wfi.word_id
    LEFT JOIN vocab.word_domains wd ON d.id = wd.word_id
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
    
    # Filter by part of speech - check if any POS for the word matches
    if part_of_speech:
        sql += " AND d.part_of_speech = %s"
        params.append(part_of_speech)
    
    # Group by term and domain
    sql += " GROUP BY d.term, wd.primary_domain"
    
    # Add sorting
    if sort_by == "rarity_asc":
        sql += " ORDER BY MIN(wfi.frequency_rank) ASC, d.term ASC"
    elif sort_by == "rarity_desc":
        sql += " ORDER BY MIN(wfi.frequency_rank) DESC, d.term ASC"
    elif sort_by == "frequency_desc":
        sql += " ORDER BY AVG(wfi.independent_frequency) DESC, d.term ASC"
    else:  # alphabetical (default)
        sql += " ORDER BY d.term ASC"
    
    sql += " LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    
    cursor.execute(sql, params)
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

def get_letter_counts_consolidated(self):
    """Get word counts by starting letter - consolidated by term"""
    conn = self.get_connection()
    cursor = conn.cursor()
    
    sql = """
    SELECT SUBSTRING(UPPER(term), 1, 1) as letter, COUNT(DISTINCT term) as count
    FROM vocab.defined
    WHERE term REGEXP '^[A-Za-z]'
    GROUP BY SUBSTRING(UPPER(term), 1, 1)
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

def get_word_details_consolidated(self, term: str):
    """Get detailed information about a specific word - all POS combined"""
    conn = self.get_connection()
    cursor = conn.cursor()
    
    sql = """
    SELECT d.term, 
           GROUP_CONCAT(DISTINCT d.definition SEPARATOR '\n\n') as definitions,
           GROUP_CONCAT(DISTINCT d.part_of_speech SEPARATOR ', ') as parts_of_speech,
           AVG(d.frequency) as avg_frequency,
           MIN(wfi.frequency_rank) as best_frequency_rank,
           AVG(wfi.independent_frequency) as avg_independent_frequency,
           AVG(wfi.rarity_percentile) as avg_rarity_percentile,
           wd.primary_domain,
           MIN(d.id) as representative_id
    FROM vocab.defined d
    LEFT JOIN vocab.word_frequencies_independent wfi ON d.id = wfi.word_id
    LEFT JOIN vocab.word_domains wd ON d.id = wd.word_id
    WHERE d.term = %s
    GROUP BY d.term, wd.primary_domain
    """
    
    cursor.execute(sql, (term,))
    result = cursor.fetchone()
    
    if not result:
        cursor.close()
        conn.close()
        return None
    
    word = {
        "id": result[8],  # representative_id
        "term": result[0],
        "definition": result[1],  # combined definitions (separated by double newlines)
        "part_of_speech": result[2],  # combined parts of speech
        "frequency": result[3],
        "frequency_rank": result[4],
        "independent_frequency": result[5],
        "rarity_percentile": result[6],
        "primary_domain": result[7]
    }
    
    cursor.close()
    conn.close()
    return word