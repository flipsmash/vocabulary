#!/usr/bin/env python3
"""
Verify database cleanup was successful
"""

import mysql.connector
from config import get_db_config

def verify_cleanup():
    try:
        db_config = get_db_config()
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Check if the removed tables still exist
        removed_tables = [
            'word_domains',
            'candidate_observations', 
            'candidate_metrics',
            'definition_candidates',
            'candidate_review_queue'
        ]
        
        print("Verifying table removal...")
        
        for table in removed_tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                print(f"  ERROR: {table} still exists!")
            except mysql.connector.Error as e:
                if "doesn't exist" in str(e):
                    print(f"  SUCCESS: {table} successfully removed")
                else:
                    print(f"  ERROR: {table} - {e}")
        
        # Get current table count
        cursor.execute("SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema = 'vocab'")
        table_count = cursor.fetchone()[0]
        
        print(f"\nCurrent database has {table_count} tables")
        print("Database cleanup verification complete!")
        
    except Exception as e:
        print(f"Error during verification: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    verify_cleanup()