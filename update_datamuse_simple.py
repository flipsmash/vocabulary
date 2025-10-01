#!/usr/bin/env python3
"""
Simple script to update frequency field using Datamuse API - first 100 terms
"""

import mysql.connector
import requests
import time
from core.config import VocabularyConfig

def get_datamuse_frequency(word: str):
    """Get word frequency from Datamuse API"""
    try:
        url = f"https://api.datamuse.com/words?sp={word}&md=f&max=1"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        if data and len(data) > 0:
            if data[0].get('word', '').lower() == word.lower():
                tags = data[0].get('tags', [])
                for tag in tags:
                    if tag.startswith('f:'):
                        return float(tag[2:])
        return None
    except Exception as e:
        print(f"Error for '{word}': {e}")
        return None

# Connect to database
config = VocabularyConfig()
conn = mysql.connector.connect(**config.get_db_config())
cursor = conn.cursor()

# Get first 100 terms without frequency
cursor.execute("""
    SELECT id, term
    FROM defined
    WHERE frequency IS NULL
    LIMIT 100
""")

terms = cursor.fetchall()
print(f"Processing {len(terms)} terms...")

for i, (term_id, term) in enumerate(terms, 1):
    print(f"{i}/100: Processing '{term}' (ID: {term_id})")

    frequency = get_datamuse_frequency(term)

    if frequency is not None:
        cursor.execute("UPDATE defined SET frequency = %s WHERE id = %s", (frequency, term_id))
        print(f"  Updated with frequency: {frequency}")
    else:
        cursor.execute("UPDATE defined SET frequency = -999 WHERE id = %s", (term_id,))
        print(f"  No frequency found, set to -999")

    # Commit every 10
    if i % 10 == 0:
        conn.commit()
        print(f"  Committed batch")

    # Rate limiting
    time.sleep(0.1)

# Final commit
conn.commit()
conn.close()

print("Complete! First 100 terms processed.")