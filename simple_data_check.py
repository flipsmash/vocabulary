#!/usr/bin/env python3
"""
Simple data quality check without unicode issues
"""

import mysql.connector
from core.config import get_db_config
import sys

def get_connection():
    config = get_db_config()
    return mysql.connector.connect(**config)

def check_browse_data():
    """Check what users see on browse page"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id, term, definition, part_of_speech 
            FROM vocab.defined 
            ORDER BY term 
            LIMIT 50
        """)
        
        results = cursor.fetchall()
        
        print("=== BROWSE PAGE DATA (First 50 alphabetical entries) ===")
        print("This is what users actually see:")
        print("-" * 60)
        
        problematic = []
        
        for i, (entry_id, term, definition, pos) in enumerate(results, 1):
            # Truncate definition for display
            def_preview = definition[:50] + "..." if definition and len(definition) > 50 else (definition or "No definition")
            
            print(f"{i:2d}. ID:{entry_id:5d} | {term:15s} | {pos:10s}")
            print(f"    Definition: {def_preview}")
            
            # Check for issues
            is_problematic = False
            issues = []
            
            if not term:
                issues.append("Missing term")
                is_problematic = True
            elif len(term) < 3 and term not in ['a', 'an', 'at', 'be', 'by', 'do', 'go', 'he', 'if', 'in', 'is', 'it', 'me', 'my', 'no', 'of', 'on', 'or', 'so', 'to', 'up', 'us', 'we']:
                issues.append("Very short word")
                is_problematic = True
                
            if term and not term.replace("-", "").replace("'", "").replace(" ", "").isalpha():
                issues.append("Contains non-alphabetic characters")
                is_problematic = True
                
            # Check for the specifically mentioned problematic terms
            if term in ['placee', 'oecodomic', 'sometimey']:
                issues.append("Specifically reported as problematic")
                is_problematic = True
                
            # Check for suspicious patterns
            if term and term.endswith('y') and len(term) > 8:
                common_y_words = ['vocabulary', 'necessary', 'dictionary', 'temporary', 'ordinary', 'military', 'category', 'history', 'mystery', 'victory', 'factory', 'memory', 'battery', 'grocery', 'summary', 'territory', 'documentary', 'contemporary', 'extraordinary']
                if term not in common_y_words:
                    issues.append("Suspicious -y ending")
                    is_problematic = True
            
            if is_problematic:
                print(f"    >>> ISSUES: {', '.join(issues)}")
                problematic.append((entry_id, term, issues))
                
            print()
            
        print(f"PROBLEMATIC ENTRIES FOUND: {len(problematic)}/{len(results)}")
        
        if problematic:
            print("\n=== SUMMARY OF PROBLEMATIC ENTRIES ===")
            for entry_id, term, issues in problematic:
                print(f"ID {entry_id}: '{term}' - {', '.join(issues)}")
                
        return results, problematic
        
    finally:
        cursor.close()
        conn.close()

def search_specific_terms():
    """Look for the specific terms mentioned"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        terms_to_find = ['placee', 'oecodomic', 'sometimey']
        
        print("=== SEARCHING FOR SPECIFICALLY REPORTED TERMS ===")
        
        found = []
        
        for term in terms_to_find:
            cursor.execute("SELECT id, term, definition FROM vocab.defined WHERE term = %s", (term,))
            result = cursor.fetchone()
            
            if result:
                entry_id, found_term, definition = result
                print(f"FOUND: '{found_term}' (ID: {entry_id})")
                print(f"Definition: {definition[:100]}...")
                found.append(result)
            else:
                print(f"NOT FOUND: '{term}'")
                
        return found
        
    finally:
        cursor.close()
        conn.close()

def get_random_sample():
    """Get random sample to see general data quality"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id, term, definition, part_of_speech 
            FROM vocab.defined 
            ORDER BY RAND() 
            LIMIT 20
        """)
        
        results = cursor.fetchall()
        
        print("=== RANDOM SAMPLE (20 entries) ===")
        
        for entry_id, term, definition, pos in results:
            def_preview = definition[:60] + "..." if definition and len(definition) > 60 else (definition or "No definition")
            print(f"ID {entry_id:5d}: {term:15s} ({pos:10s}) - {def_preview}")
            
        return results
        
    finally:
        cursor.close()
        conn.close()

def get_stats():
    """Get basic statistics"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM vocab.defined")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE definition IS NULL OR definition = ''")
        no_def = cursor.fetchone()[0]
        
        cursor.execute("SELECT MIN(LENGTH(term)), MAX(LENGTH(term)), AVG(LENGTH(term)) FROM vocab.defined WHERE term IS NOT NULL")
        min_len, max_len, avg_len = cursor.fetchone()
        
        print("=== DATABASE STATISTICS ===")
        print(f"Total entries: {total:,}")
        print(f"Entries without definition: {no_def:,} ({no_def/total*100:.1f}%)")
        print(f"Term length - Min: {min_len}, Max: {max_len}, Average: {avg_len:.1f}")
        
        return total, no_def, min_len, max_len, avg_len
        
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print("Simple vocabulary database investigation...")
    print("=" * 60)
    
    try:
        # Check what browse page shows
        browse_results, problematic = check_browse_data()
        
        # Search for specific problematic terms
        found_terms = search_specific_terms()
        
        # Get random sample
        random_sample = get_random_sample()
        
        # Get overall stats
        stats = get_stats()
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        
        if found_terms:
            print(f"Found {len(found_terms)} specifically reported problematic terms")
        else:
            print("None of the specifically reported terms were found")
            
        print(f"Browse page shows {len(problematic)} problematic entries out of first 50")
        
        if len(problematic) > 10:
            print("WARNING: High number of problematic entries detected!")
        elif len(problematic) > 0:
            print("NOTICE: Some problematic entries found")
        else:
            print("Browse page entries appear normal")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()