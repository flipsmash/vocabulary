#!/usr/bin/env python3
"""
Check if candidates table exists
"""

import mysql.connector
from core.config import get_db_config

def check_candidates_table():
    """Check if candidate_words table exists"""
    config = get_db_config()
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor()
    
    try:
        # Check if candidate_words table exists
        cursor.execute("SHOW TABLES LIKE 'candidate_words'")
        result = cursor.fetchone()
        
        if result:
            print("candidate_words table exists")
            
            # Get table structure
            cursor.execute("DESCRIBE candidate_words")
            columns = cursor.fetchall()
            print("\nTable structure:")
            for column in columns:
                print(f"  {column[0]}: {column[1]}")
                
            # Count records
            cursor.execute("SELECT COUNT(*) FROM vocab.candidate_words")
            count = cursor.fetchone()[0]
            print(f"\nTotal records: {count}")
            
            if count > 0:
                # Show sample records
                cursor.execute("SELECT id, term, review_status, utility_score FROM vocab.candidate_words LIMIT 5")
                samples = cursor.fetchall()
                print("\nSample records:")
                for sample in samples:
                    print(f"  ID: {sample[0]}, Term: {sample[1]}, Status: {sample[2]}, Score: {sample[3]}")
                    
        else:
            print("candidate_words table does not exist")
            
            # Check for similar tables
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            print("\nAvailable tables:")
            for table in tables:
                table_name = table[0]
                if 'candidate' in table_name.lower():
                    print(f"  {table_name} (contains 'candidate')")
                else:
                    print(f"  {table_name}")
        
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    check_candidates_table()