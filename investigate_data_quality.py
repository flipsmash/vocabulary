#!/usr/bin/env python3
"""
Data Quality Investigation Script
Analyzes the vocabulary database for potential data quality issues
"""

import mysql.connector
from core.config import get_db_config
import re
from collections import Counter
import json

def get_connection():
    """Get database connection"""
    config = get_db_config()
    return mysql.connector.connect(**config)

def analyze_word_patterns():
    """Analyze patterns in vocabulary words to identify potential issues"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Get sample of words with their details
        cursor.execute("""
            SELECT id, term, definition, part_of_speech, frequency, domain 
            FROM defined 
            ORDER BY id 
            LIMIT 100
        """)
        
        sample_words = cursor.fetchall()
        
        print("=== SAMPLE VOCABULARY ENTRIES ===")
        print("ID | Term | Part of Speech | Domain | Frequency | Definition Preview")
        print("-" * 100)
        
        suspicious_words = []
        
        for word_data in sample_words:
            word_id, term, definition, pos, frequency, domain = word_data
            definition_preview = (definition[:60] + "...") if definition and len(definition) > 60 else (definition or "No definition")
            
            print(f"{word_id:4d} | {term:12s} | {pos:12s} | {domain:15s} | {frequency:8.2f} | {definition_preview}")
            
            # Check for suspicious patterns
            if term and (
                len(term) < 3 or  # Very short words
                not term.isalpha() or  # Non-alphabetic characters
                any(char.isupper() and i > 0 for i, char in enumerate(term)) or  # Mid-word capitals
                term.endswith('y') and len(term) > 8  # Suspicious 'y' endings
            ):
                suspicious_words.append((word_id, term, "Suspicious pattern"))
        
        print(f"\n=== SUSPICIOUS WORDS DETECTED ===")
        if suspicious_words:
            for word_id, term, reason in suspicious_words:
                print(f"ID {word_id}: '{term}' - {reason}")
        else:
            print("No suspicious patterns detected in this sample")
            
        return sample_words, suspicious_words
        
    finally:
        cursor.close()
        conn.close()

def check_data_statistics():
    """Get overall database statistics"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Total word count
        cursor.execute("SELECT COUNT(*) FROM defined")
        total_words = cursor.fetchone()[0]
        
        # Words without definitions
        cursor.execute("SELECT COUNT(*) FROM defined WHERE definition IS NULL OR definition = ''")
        no_definition = cursor.fetchone()[0]
        
        # Average word length
        cursor.execute("SELECT AVG(LENGTH(term)) FROM defined WHERE term IS NOT NULL")
        avg_length = cursor.fetchone()[0]
        
        # Most common parts of speech
        cursor.execute("""
            SELECT part_of_speech, COUNT(*) as count 
            FROM defined 
            WHERE part_of_speech IS NOT NULL 
            GROUP BY part_of_speech 
            ORDER BY count DESC 
            LIMIT 10
        """)
        pos_counts = cursor.fetchall()
        
        # Most common domains
        cursor.execute("""
            SELECT domain, COUNT(*) as count 
            FROM defined 
            WHERE domain IS NOT NULL 
            GROUP BY domain 
            ORDER BY count DESC 
            LIMIT 10
        """)
        domain_counts = cursor.fetchall()
        
        # Frequency distribution
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                MIN(frequency) as min_freq,
                MAX(frequency) as max_freq,
                AVG(frequency) as avg_freq
            FROM defined 
            WHERE frequency IS NOT NULL
        """)
        freq_stats = cursor.fetchone()
        
        print(f"\n=== DATABASE STATISTICS ===")
        print(f"Total words: {total_words:,}")
        print(f"Words without definitions: {no_definition:,} ({no_definition/total_words*100:.1f}%)")
        print(f"Average word length: {avg_length:.1f} characters")
        
        print(f"\n=== FREQUENCY STATISTICS ===")
        if freq_stats[0] > 0:
            total, min_freq, max_freq, avg_freq = freq_stats
            print(f"Words with frequency data: {total:,}")
            print(f"Frequency range: {min_freq:.2f} to {max_freq:.2f}")
            print(f"Average frequency: {avg_freq:.2f}")
        else:
            print("No frequency data available")
        
        print(f"\n=== TOP PARTS OF SPEECH ===")
        for pos, count in pos_counts:
            print(f"{pos}: {count:,} words")
        
        print(f"\n=== TOP DOMAINS ===")
        for domain, count in domain_counts:
            print(f"{domain}: {count:,} words")
            
        return {
            'total_words': total_words,
            'no_definition': no_definition,
            'avg_length': avg_length,
            'pos_counts': pos_counts,
            'domain_counts': domain_counts,
            'freq_stats': freq_stats
        }
        
    finally:
        cursor.close()
        conn.close()

def find_problematic_entries():
    """Find entries that match the UX reviewer's complaints"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Look for the specific words mentioned
        problematic_terms = ['placee', 'oecodomic', 'sometimey']
        
        print(f"\n=== SEARCHING FOR REPORTED PROBLEMATIC TERMS ===")
        
        found_issues = []
        
        for term in problematic_terms:
            cursor.execute("SELECT id, term, definition, part_of_speech, frequency FROM defined WHERE term = %s", (term,))
            result = cursor.fetchone()
            
            if result:
                print(f"FOUND: {term}")
                print(f"  ID: {result[0]}")
                print(f"  Term: {result[1]}")
                print(f"  Definition: {result[2]}")
                print(f"  Part of Speech: {result[3]}")
                print(f"  Frequency: {result[4]}")
                print()
                found_issues.append(result)
            else:
                print(f"NOT FOUND: {term}")
        
        # Look for patterns that might indicate corrupted data
        print(f"\n=== LOOKING FOR PATTERN-BASED ISSUES ===")
        
        # Words ending in 'y' that might be corrupted
        cursor.execute("""
            SELECT id, term, definition, part_of_speech 
            FROM defined 
            WHERE term LIKE '%y' 
            AND LENGTH(term) > 6
            AND term NOT IN ('vocabulary', 'necessary', 'temporary', 'dictionary', 'ordinary', 'primary', 'secondary', 'military', 'category', 'history', 'mystery', 'victory', 'factory', 'memory', 'battery', 'grocery', 'summary', 'territory')
            LIMIT 20
        """)
        
        suspicious_y_words = cursor.fetchall()
        print(f"Words ending in 'y' (potentially suspicious): {len(suspicious_y_words)}")
        for word_data in suspicious_y_words[:10]:  # Show first 10
            word_id, term, definition, pos = word_data
            def_preview = (definition[:50] + "...") if definition and len(definition) > 50 else (definition or "No definition")
            print(f"  {word_id}: '{term}' ({pos}) - {def_preview}")
        
        # Very short words (might be fragments)
        cursor.execute("""
            SELECT id, term, definition, part_of_speech 
            FROM defined 
            WHERE LENGTH(term) <= 2
            AND term NOT IN ('a', 'an', 'at', 'be', 'by', 'do', 'go', 'he', 'if', 'in', 'is', 'it', 'me', 'my', 'no', 'of', 'on', 'or', 'so', 'to', 'up', 'us', 'we')
            LIMIT 20
        """)
        
        short_words = cursor.fetchall()
        print(f"\nVery short words (potentially fragments): {len(short_words)}")
        for word_data in short_words[:10]:
            word_id, term, definition, pos = word_data
            def_preview = (definition[:50] + "...") if definition and len(definition) > 50 else (definition or "No definition")
            print(f"  {word_id}: '{term}' ({pos}) - {def_preview}")
            
        return found_issues, suspicious_y_words, short_words
        
    finally:
        cursor.close()
        conn.close()

def check_browse_page_data():
    """Check what data is actually being served to the browse page"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Get the first page of browse results (mimicking the web app query)
        cursor.execute("""
            SELECT id, term, definition, part_of_speech, frequency, domain
            FROM defined 
            ORDER BY term 
            LIMIT 25
        """)
        
        browse_results = cursor.fetchall()
        
        print(f"\n=== BROWSE PAGE DATA (First 25 entries) ===")
        print("This is what users see on the browse page:")
        print("-" * 80)
        
        for i, (word_id, term, definition, pos, frequency, domain) in enumerate(browse_results, 1):
            def_preview = (definition[:60] + "...") if definition and len(definition) > 60 else (definition or "No definition")
            print(f"{i:2d}. {term:15s} ({pos:10s}) - {def_preview}")
            
            # Flag potentially problematic entries
            if term and (
                not term.isalpha() or 
                len(term) <= 2 or 
                term.endswith('y') and len(term) > 8 and term not in ['vocabulary', 'necessary', 'dictionary']
            ):
                print(f"    ⚠️  POTENTIALLY PROBLEMATIC ENTRY")
        
        return browse_results
        
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print("Starting vocabulary database quality analysis...")
    print("=" * 60)
    
    try:
        # Run all analyses
        sample_words, suspicious_words = analyze_word_patterns()
        stats = check_data_statistics()
        issues, suspicious_y, short_words = find_problematic_entries()
        browse_data = check_browse_page_data()
        
        print(f"\n" + "=" * 60)
        print("ANALYSIS COMPLETE")
        print(f"=" * 60)
        print(f"Database contains {stats['total_words']:,} total words")
        print(f"Found {len(suspicious_words)} suspicious patterns in sample")
        print(f"Found {len(short_words)} very short words")
        print(f"Words without definitions: {stats['no_definition']:,}")
        
        if len(issues) > 0 or len(suspicious_words) > 0 or len(short_words) > 0:
            print(f"\n⚠️  DATA QUALITY ISSUES DETECTED")
            print(f"Immediate attention recommended for data cleanup")
        else:
            print(f"\n✅ No obvious data quality issues detected")
            print(f"Further investigation may be needed")
            
    except Exception as e:
        print(f"Error during analysis: {e}")
        import traceback
        traceback.print_exc()