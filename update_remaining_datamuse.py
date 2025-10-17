#!/usr/bin/env python3
"""
Continue updating remaining terms with Datamuse API frequencies
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

# Get all remaining terms without frequency
cursor.execute("""
    SELECT id, term
    FROM vocab.defined
    WHERE frequency IS NULL
    ORDER BY id
""")

terms = cursor.fetchall()
total_terms = len(terms)
print(f"Processing {total_terms} remaining terms...")

updated_count = 0
not_found_count = 0

for i, (term_id, term) in enumerate(terms, 1):
    print(f"{i}/{total_terms}: Processing '{term}' (ID: {term_id})")

    frequency = get_datamuse_frequency(term)

    if frequency is not None:
        cursor.execute("UPDATE vocab.defined SET frequency = %s WHERE id = %s", (frequency, term_id))
        updated_count += 1
        print(f"  Updated with frequency: {frequency}")
    else:
        cursor.execute("UPDATE vocab.defined SET frequency = -999 WHERE id = %s", (term_id,))
        not_found_count += 1
        print(f"  No frequency found, set to -999")

    # Commit every 50
    if i % 50 == 0:
        conn.commit()
        print(f"  Committed batch {i//50} - Progress: {i}/{total_terms} ({100*i/total_terms:.1f}%)")

    # Rate limiting - be respectful to the API
    time.sleep(0.2)  # 200ms delay between requests

    # Longer pause every 100 requests
    if i % 100 == 0:
        print(f"  Pausing for rate limiting...")
        time.sleep(5.0)  # 5 second pause

# Final commit
conn.commit()
conn.close()

print(f"\nUpdate complete!")
print(f"Terms updated with Datamuse frequency: {updated_count}")
print(f"Terms set to -999 (no frequency found): {not_found_count}")
print(f"Total processed: {total_terms}")