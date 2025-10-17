#!/usr/bin/env python3
"""
Quick script to restore basic domain classifications to word_domains table
Uses simple keyword matching for common domains
"""

import mysql.connector
import re
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import get_db_config
from collections import defaultdict

def get_simple_domain(term, definition, part_of_speech):
    """Simple domain classification based on keywords"""
    
    # Combine term and definition for analysis
    text = f"{term} {definition}".lower()
    
    # Define domain patterns (simplified version)
    domain_patterns = {
        'Medical': [r'\b(medical|medicine|doctor|patient|hospital|disease|health|anatomy|symptom|treatment|therapy|diagnosis|surgical|clinical)\b',
                   r'\b(blood|heart|brain|lung|kidney|liver|bone|muscle|nerve|cell|tissue|organ)\b'],
        
        'Scientific': [r'\b(science|research|study|experiment|theory|hypothesis|analysis|data|method|laboratory)\b',
                      r'\b(physics|chemistry|biology|mathematics|equation|formula|calculation|measurement)\b'],
        
        'Legal': [r'\b(legal|law|court|judge|lawyer|attorney|contract|agreement|rights|justice|trial|case)\b',
                 r'\b(legislative|judicial|constitutional|criminal|civil|defendant|plaintiff|evidence)\b'],
        
        'Technology': [r'\b(computer|software|technology|digital|electronic|internet|network|system|program|data)\b',
                      r'\b(algorithm|database|hardware|coding|programming|artificial|intelligence|cyber)\b'],
        
        'Business': [r'\b(business|company|corporation|management|marketing|finance|economy|trade|commerce|industry)\b',
                    r'\b(profit|investment|market|customer|client|sales|revenue|budget|accounting)\b'],
        
        'Arts': [r'\b(art|artistic|creative|design|music|musical|literature|poetry|painting|sculpture)\b',
                r'\b(aesthetic|beautiful|style|culture|cultural|entertainment|performance|theater)\b'],
        
        'Education': [r'\b(education|school|university|college|teacher|student|academic|learning|knowledge)\b',
                     r'\b(curriculum|instruction|pedagogy|scholarly|intellectual|educational)\b'],
        
        'Architecture': [r'\b(building|architecture|construction|structure|design|engineering|foundation)\b',
                        r'\b(architectural|structural|blueprint|construction|infrastructure)\b'],
        
        'Geography': [r'\b(geography|geographic|location|place|region|area|territory|landscape|environment)\b',
                     r'\b(mountain|river|ocean|continent|country|city|climate|geological)\b'],
        
        'Biology': [r'\b(biological|organism|species|evolution|genetics|cell|dna|protein|enzyme)\b',
                   r'\b(plant|animal|ecology|ecosystem|biodiversity|habitat|evolutionary)\b'],
        
        'Psychology': [r'\b(psychology|psychological|mental|mind|behavior|cognitive|emotional|personality)\b',
                      r'\b(consciousness|perception|memory|learning|motivation|psychiatric)\b']
    }
    
    # Score each domain
    domain_scores = defaultdict(int)
    
    for domain, patterns in domain_patterns.items():
        for pattern in patterns:
            matches = len(re.findall(pattern, text))
            domain_scores[domain] += matches
    
    # Special handling for part of speech
    if part_of_speech == 'NOUN':
        # Nouns are more likely to be concrete domain-specific terms
        for domain in domain_scores:
            domain_scores[domain] *= 1.2
    
    # Return the highest scoring domain, or 'General' if no clear match
    if not domain_scores:
        return 'General'
    
    best_domain = max(domain_scores.items(), key=lambda x: x[1])
    
    # Require at least 1 match to assign a specific domain
    if best_domain[1] >= 1:
        return best_domain[0]
    else:
        return 'General'

def populate_word_domains():
    """Populate word_domains table with basic classifications"""
    
    config = get_db_config()
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor()
    
    print("Fetching words from defined table...")
    cursor.execute("SELECT id, term, definition, part_of_speech FROM vocab.defined WHERE definition IS NOT NULL")
    words = cursor.fetchall()
    
    print(f"Processing {len(words)} words...")
    
    # Clear existing data
    cursor.execute("DELETE FROM vocab.word_domains")
    conn.commit()
    
    # Process in batches
    batch_size = 1000
    insert_data = []
    
    for i, (word_id, term, definition, pos) in enumerate(words):
        if not definition:
            continue
            
        domain = get_simple_domain(term, definition, pos)
        insert_data.append((word_id, domain))
        
        if len(insert_data) >= batch_size:
            cursor.executemany(
                "INSERT INTO vocab.word_domains (word_id, primary_domain) VALUES (%s, %s)",
                insert_data
            )
            conn.commit()
            print(f"Processed {i+1}/{len(words)} words...")
            insert_data = []
    
    # Insert remaining data
    if insert_data:
        cursor.executemany(
            "INSERT INTO vocab.word_domains (word_id, primary_domain) VALUES (%s, %s)",
            insert_data
        )
        conn.commit()
    
    # Show domain distribution
    print("\nDomain distribution:")
    cursor.execute("SELECT primary_domain, COUNT(*) FROM vocab.word_domains GROUP BY primary_domain ORDER BY COUNT(*) DESC")
    for domain, count in cursor.fetchall():
        print(f"  {domain}: {count}")
    
    cursor.close()
    conn.close()
    print(f"\nSuccessfully populated word_domains table with {len(words)} classifications!")

if __name__ == "__main__":
    populate_word_domains()