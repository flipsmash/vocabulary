#!/usr/bin/env python3
"""
Final verification of database cleanup
"""

import mysql.connector
from config import get_db_config

def final_verification():
    try:
        db_config = get_db_config()
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        # Get all remaining tables
        cursor.execute("""
            SELECT TABLE_NAME as table_name, TABLE_ROWS as table_rows, 
                   ROUND((DATA_LENGTH + INDEX_LENGTH)/1024/1024, 2) as size_mb
            FROM information_schema.tables 
            WHERE table_schema = 'vocab'
            ORDER BY size_mb DESC
        """)
        
        tables = cursor.fetchall()
        
        print("DATABASE CLEANUP VERIFICATION")
        print("=" * 50)
        print(f"Total tables: {len(tables)}")
        
        # Check for any empty tables
        empty_tables = [t for t in tables if t['table_rows'] == 0]
        if empty_tables:
            print(f"\nEmpty tables found: {len(empty_tables)}")
            for table in empty_tables:
                print(f"  - {table['table_name']} ({table['size_mb']} MB)")
        else:
            print("\nNo empty tables found - database is clean!")
        
        # Show largest tables for reference
        print(f"\nLargest tables (top 5):")
        for table in tables[:5]:
            print(f"  - {table['table_name']:<25} {table['size_mb']:>8.2f} MB  {table['table_rows']:>10,} rows")
        
        # Check if the removed tables are truly gone
        removed_tables = [
            'word_domains', 'candidate_observations', 'candidate_metrics', 
            'definition_candidates', 'candidate_review_queue'
        ]
        
        still_exist = []
        for table_name in removed_tables:
            cursor.execute(f"""
                SELECT COUNT(*) as count FROM information_schema.tables 
                WHERE table_schema = 'vocab' AND table_name = '{table_name}'
            """)
            if cursor.fetchone()['count'] > 0:
                still_exist.append(table_name)
        
        if still_exist:
            print(f"\nWARNING: These tables still exist: {still_exist}")
        else:
            print(f"\nSUCCESS: All targeted tables successfully removed")
            print("Database cleanup is complete!")
        
        # Calculate total database size
        total_size = sum(table['size_mb'] for table in tables)
        print(f"\nTotal database size: {total_size:,.2f} MB")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    final_verification()