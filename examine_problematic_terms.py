#!/usr/bin/env python3
"""
Detailed examination of the problematic terms found by UX review
"""

import mysql.connector
from core.config import get_db_config

def get_connection():
    config = get_db_config()
    return mysql.connector.connect(**config)

def examine_specific_terms():
    """Examine the specific problematic terms in detail"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        problematic_terms = ['placee', 'oecodomic', 'sometimey']
        
        print("=== DETAILED EXAMINATION OF PROBLEMATIC TERMS ===")
        print()
        
        all_findings = []
        
        for term in problematic_terms:
            cursor.execute("""
                SELECT id, term, definition, part_of_speech, frequency, 
                       word_source, definition_source, bad, python_wordfreq
                FROM defined 
                WHERE term = %s
            """, (term,))
            
            results = cursor.fetchall()
            
            if results:
                for result in results:
                    (entry_id, found_term, definition, pos, frequency, 
                     word_source, def_source, bad, py_wordfreq) = result
                    
                    print(f"TERM: '{found_term}' (ID: {entry_id})")
                    print(f"  Definition: {definition}")
                    print(f"  Part of Speech: {pos}")
                    print(f"  Frequency: {frequency}")
                    print(f"  Python WordFreq: {py_wordfreq}")
                    print(f"  Word Source: {word_source}")
                    print(f"  Definition Source: {def_source}")
                    print(f"  Bad Flag: {bad}")
                    print()
                    
                    # Analysis
                    analysis = analyze_term_validity(found_term, definition, frequency, py_wordfreq)
                    print(f"  ANALYSIS: {analysis}")
                    print()
                    
                    all_findings.append({
                        'id': entry_id,
                        'term': found_term,
                        'definition': definition,
                        'analysis': analysis
                    })
                    
            else:
                print(f"TERM: '{term}' - NOT FOUND")
                
        return all_findings
        
    finally:
        cursor.close()
        conn.close()

def analyze_term_validity(term, definition, frequency, py_wordfreq):
    """Analyze whether a term appears to be legitimate or problematic"""
    issues = []
    
    # Check term patterns
    if not term.replace("-", "").replace("'", "").isalpha():
        issues.append("Contains non-alphabetic characters")
        
    if len(term) < 3:
        issues.append("Very short")
        
    # Check definition quality
    if not definition or len(definition.strip()) < 10:
        issues.append("Poor or missing definition")
        
    # Check frequency data consistency
    if frequency and py_wordfreq:
        freq_ratio = frequency / py_wordfreq if py_wordfreq > 0 else float('inf')
        if freq_ratio > 100 or freq_ratio < 0.01:
            issues.append("Frequency data inconsistent")
    
    # Specific term analysis
    if term == 'placee':
        # This is actually a legitimate finance term
        if 'investor' in definition.lower() or 'placement' in definition.lower():
            issues.append("Legitimate but specialized finance term - might confuse general users")
        else:
            issues.append("Definition doesn't match expected finance term")
            
    elif term == 'oecodomic':
        # This appears to be archaic/obsolete
        if 'obsolete' in definition.lower() or 'household' in definition.lower():
            issues.append("Legitimate but obsolete term - low educational value")
        else:
            issues.append("Unclear or incorrect definition")
            
    elif term == 'sometimey':
        # This appears to be dialectal/informal
        if 'former' in definition.lower() or 'occasional' in definition.lower():
            issues.append("Legitimate but dialectal/informal - questionable for general vocabulary")
        else:
            issues.append("Unclear definition")
    
    if not issues:
        return "Appears legitimate"
    else:
        return "; ".join(issues)

def find_similar_problematic_patterns():
    """Find other terms with similar patterns to the problematic ones"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        print("=== SEARCHING FOR SIMILAR PROBLEMATIC PATTERNS ===")
        print()
        
        # Look for other terms ending in 'ee' (like placee)
        print("1. Terms ending in 'ee' (similar to 'placee'):")
        cursor.execute("""
            SELECT term, definition, frequency
            FROM defined 
            WHERE term LIKE '%ee' 
            AND LENGTH(term) > 4
            AND term NOT IN ('employee', 'committee', 'guarantee', 'refugee', 'trustee', 'nominee', 'degree', 'agree')
            LIMIT 10
        """)
        
        ee_results = cursor.fetchall()
        for term, definition, freq in ee_results:
            def_preview = definition[:50] + "..." if definition and len(definition) > 50 else (definition or "No def")
            print(f"  {term}: {def_preview} (freq: {freq})")
        print()
        
        # Look for other archaic/obsolete terms (like oecodomic)
        print("2. Other obsolete/archaic terms:")
        cursor.execute("""
            SELECT term, definition, frequency
            FROM defined 
            WHERE definition LIKE '%obsolete%' 
            OR definition LIKE '%archaic%'
            OR definition LIKE '%rare%'
            LIMIT 10
        """)
        
        archaic_results = cursor.fetchall()
        for term, definition, freq in archaic_results:
            def_preview = definition[:50] + "..." if definition and len(definition) > 50 else (definition or "No def")
            print(f"  {term}: {def_preview} (freq: {freq})")
        print()
        
        # Look for other informal/dialectal terms (like sometimey)
        print("3. Terms ending in 'ey' (similar to 'sometimey'):")
        cursor.execute("""
            SELECT term, definition, frequency
            FROM defined 
            WHERE term LIKE '%ey' 
            AND LENGTH(term) > 6
            AND term NOT IN ('journey', 'money', 'honey', 'survey', 'turkey', 'hockey', 'whiskey', 'kidney', 'chimney', 'attorney')
            LIMIT 10
        """)
        
        ey_results = cursor.fetchall()
        for term, definition, freq in ey_results:
            def_preview = definition[:50] + "..." if definition and len(definition) > 50 else (definition or "No def")
            print(f"  {term}: {def_preview} (freq: {freq})")
        print()
        
        return ee_results, archaic_results, ey_results
        
    finally:
        cursor.close()
        conn.close()

def check_data_sources():
    """Check what sources these problematic terms came from"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        print("=== DATA SOURCE ANALYSIS ===")
        print()
        
        # Check word sources
        cursor.execute("""
            SELECT word_source, COUNT(*) as count
            FROM defined 
            WHERE word_source IS NOT NULL
            GROUP BY word_source
            ORDER BY count DESC
        """)
        
        word_sources = cursor.fetchall()
        print("Word Sources:")
        for source, count in word_sources:
            print(f"  {source}: {count:,} words")
        print()
        
        # Check definition sources
        cursor.execute("""
            SELECT definition_source, COUNT(*) as count
            FROM defined 
            WHERE definition_source IS NOT NULL
            GROUP BY definition_source
            ORDER BY count DESC
        """)
        
        def_sources = cursor.fetchall()
        print("Definition Sources:")
        for source, count in def_sources:
            print(f"  {source}: {count:,} definitions")
        print()
        
        # Check if problematic terms have specific source patterns
        cursor.execute("""
            SELECT term, word_source, definition_source
            FROM defined 
            WHERE term IN ('placee', 'oecodomic', 'sometimey')
        """)
        
        problematic_sources = cursor.fetchall()
        print("Problematic Terms Sources:")
        for term, word_src, def_src in problematic_sources:
            print(f"  {term}: word_source={word_src}, definition_source={def_src}")
        print()
        
        return word_sources, def_sources, problematic_sources
        
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print("Detailed examination of problematic vocabulary terms...")
    print("=" * 60)
    
    try:
        # Examine the specific problematic terms
        findings = examine_specific_terms()
        
        # Look for similar patterns
        similar_patterns = find_similar_problematic_patterns()
        
        # Check data sources
        sources = check_data_sources()
        
        print("=" * 60)
        print("SUMMARY OF FINDINGS")
        print("=" * 60)
        
        print("The UX reviewer was correct - these terms exist in the database:")
        for finding in findings:
            print(f"- {finding['term']} (ID: {finding['id']}): {finding['analysis']}")
        
        print("\nRECOMMENDations:")
        print("1. These are legitimate English words but may be poor choices for a general vocabulary app")
        print("2. Consider filtering out highly specialized, obsolete, or dialectal terms")
        print("3. Focus on more common, educationally valuable vocabulary")
        print("4. Implement quality scoring based on frequency, usage, and educational value")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()