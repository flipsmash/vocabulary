#!/usr/bin/env python3
"""
Database Schema Investigation
Check the actual structure and sample data
"""

import mysql.connector
from core.config import get_db_config

def get_connection():
    """Get database connection"""
    config = get_db_config()
    return mysql.connector.connect(**config)

def check_table_schema():
    """Check the actual table structure"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Show table structure
        cursor.execute("DESCRIBE defined")
        columns = cursor.fetchall()
        
        print("=== DEFINED TABLE SCHEMA ===")
        print("Column | Type | Null | Key | Default | Extra")
        print("-" * 60)
        for column in columns:
            print(" | ".join(str(x) if x is not None else "NULL" for x in column))
            
        return [col[0] for col in columns]  # Return column names
        
    finally:
        cursor.close()
        conn.close()

def check_sample_data(columns):
    """Check sample data using actual column names"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Build query with actual columns
        column_list = ", ".join(columns)
        
        cursor.execute(f"SELECT {column_list} FROM vocab.defined ORDER BY id LIMIT 20")
        sample_data = cursor.fetchall()
        
        print(f"\n=== SAMPLE DATA (First 20 entries) ===")
        print(" | ".join(columns))
        print("-" * 80)
        
        suspicious_entries = []
        
        for row in sample_data:
            # Print the row
            row_str = " | ".join(str(x)[:15] if x is not None else "NULL" for x in row)
            print(row_str)
            
            # Check for suspicious patterns in the term (usually 2nd column based on typical schema)
            if len(row) > 1 and row[1]:  # Assuming 'term' is the second column
                term = row[1]
                if (not term.replace("-", "").replace("'", "").isalpha() or 
                    len(term) < 3 or 
                    any(char.isupper() and i > 0 for i, char in enumerate(term))):
                    suspicious_entries.append((row[0], term, "Suspicious pattern"))
        
        print(f"\n=== SUSPICIOUS ENTRIES FOUND ===")
        if suspicious_entries:
            for entry_id, term, reason in suspicious_entries:
                print(f"ID {entry_id}: '{term}' - {reason}")
        else:
            print("No obvious suspicious patterns in this sample")
            
        return sample_data, suspicious_entries
        
    finally:
        cursor.close()
        conn.close()

def check_browse_query():
    """Check what the browse page actually queries"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # This mimics what the browse page likely does
        cursor.execute("""
            SELECT id, term, definition, part_of_speech 
            FROM vocab.defined 
            ORDER BY term 
            LIMIT 25
        """)
        
        browse_results = cursor.fetchall()
        
        print(f"\n=== BROWSE PAGE RESULTS (What users actually see) ===")
        print("ID | Term | Definition Preview | Part of Speech")
        print("-" * 80)
        
        problematic_count = 0
        
        for entry_id, term, definition, pos in browse_results:
            def_preview = (definition[:40] + "...") if definition and len(definition) > 40 else (definition or "No def")
            print(f"{entry_id:4d} | {term:12s} | {def_preview:42s} | {pos or 'None'}")
            
            # Check if this looks problematic
            if term and (
                not term.replace("-", "").replace("'", "").isalpha() or
                len(term) < 3 or
                term in ['placee', 'oecodomic', 'sometimey'] or
                (term.endswith('y') and len(term) > 8 and 
                 term not in ['vocabulary', 'necessary', 'dictionary', 'temporary', 'ordinary'])
            ):
                problematic_count += 1
                print(f"     ⚠️  POTENTIALLY PROBLEMATIC")
        
        print(f"\nProblematic entries found: {problematic_count}/{len(browse_results)}")
        
        return browse_results, problematic_count
        
    finally:
        cursor.close()
        conn.close()

def search_specific_terms():
    """Look for the specific terms mentioned in the UX review"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        problematic_terms = ['placee', 'oecodomic', 'sometimey']
        
        print(f"\n=== SEARCHING FOR REPORTED PROBLEMATIC TERMS ===")
        
        found_terms = []
        
        for term in problematic_terms:
            cursor.execute("SELECT id, term, definition FROM vocab.defined WHERE term = %s", (term,))
            result = cursor.fetchone()
            
            if result:
                entry_id, found_term, definition = result
                print(f"FOUND: '{found_term}' (ID: {entry_id})")
                print(f"  Definition: {definition}")
                print()
                found_terms.append(result)
            else:
                print(f"NOT FOUND: '{term}'")
        
        return found_terms
        
    finally:
        cursor.close()
        conn.close()

def get_database_stats():
    """Get basic database statistics"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM vocab.defined")
        total_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE definition IS NULL OR definition = ''")
        no_definition = cursor.fetchone()[0]
        
        cursor.execute("SELECT AVG(LENGTH(term)) FROM vocab.defined WHERE term IS NOT NULL")
        avg_length = cursor.fetchone()[0]
        
        print(f"\n=== DATABASE STATISTICS ===")
        print(f"Total words: {total_count:,}")
        print(f"Words without definitions: {no_definition:,} ({no_definition/total_count*100:.1f}%)")
        print(f"Average word length: {avg_length:.1f} characters")
        
        return total_count, no_definition, avg_length
        
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print("Investigating vocabulary database schema and data quality...")
    print("=" * 70)
    
    try:
        # Check schema first
        columns = check_table_schema()
        
        # Check sample data
        sample_data, suspicious = check_sample_data(columns)
        
        # Check browse results
        browse_data, problematic_count = check_browse_query()
        
        # Search for specific problematic terms
        found_terms = search_specific_terms()
        
        # Get overall stats
        total, no_def, avg_len = get_database_stats()
        
        print(f"\n" + "=" * 70)
        print("INVESTIGATION SUMMARY")
        print("=" * 70)
        
        if found_terms:
            print(f"✅ Found {len(found_terms)} of the reported problematic terms")
        else:
            print(f"❌ None of the specifically reported terms found")
            
        if problematic_count > 0:
            print(f"⚠️  {problematic_count}/25 entries on browse page appear problematic")
        else:
            print(f"✅ Browse page entries look normal")
            
        if len(suspicious) > 0:
            print(f"⚠️  {len(suspicious)} suspicious patterns detected in sample")
        else:
            print(f"✅ No suspicious patterns in sample data")
            
        print(f"\nDatabase contains {total:,} total entries")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()