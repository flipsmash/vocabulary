#!/usr/bin/env python3
"""
Check existing progress tracking tables in the database
"""

import mysql.connector
from config import get_db_config

def check_progress_tables():
    try:
        db_config = get_db_config()
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        print("Checking for existing progress tracking tables...")
        
        # Check for any session or progress related tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'vocab' 
            AND (table_name LIKE '%session%' 
                 OR table_name LIKE '%progress%' 
                 OR table_name LIKE '%harvest%'
                 OR table_name LIKE '%tracking%')
        """)
        
        tables = cursor.fetchall()
        
        if tables:
            print("Found existing progress tracking tables:")
            for table in tables:
                print(f"  - {table[0]}")
                
                # Show table structure
                cursor.execute(f"DESCRIBE {table[0]}")
                columns = cursor.fetchall()
                print(f"    Columns: {[col[0] for col in columns]}")
        else:
            print("No existing progress tracking tables found")
            
        # Check all tables to see what's available
        print("\nAll tables in database:")
        cursor.execute("SHOW TABLES")
        all_tables = cursor.fetchall()
        for table in all_tables:
            print(f"  - {table[0]}")
            
    except Exception as e:
        print(f"Error checking tables: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    check_progress_tables()