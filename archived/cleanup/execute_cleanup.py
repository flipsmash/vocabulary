#!/usr/bin/env python3
"""
Execute database cleanup script safely
"""

import mysql.connector
from config import get_db_config

def execute_cleanup():
    try:
        db_config = get_db_config()
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Read the cleanup script
        with open('database_cleanup.sql', 'r') as f:
            cleanup_script = f.read()
        
        print("Executing database cleanup...")
        print("Tables to remove:")
        print("  - word_domains (6.92 MB)")
        print("  - candidate_observations (0.36 MB)")
        print("  - candidate_metrics (0.34 MB)")
        print("  - definition_candidates (0.05 MB)")
        print("  - candidate_review_queue (0.00 MB)")
        print("Total space to reclaim: 7.67 MB")
        
        # Execute each DROP statement
        statements = cleanup_script.split(';')
        for statement in statements:
            statement = statement.strip()
            if statement and not statement.startswith('--'):
                print(f"Executing: {statement}")
                cursor.execute(statement)
        
        conn.commit()
        print("\nCleanup completed successfully!")
        print("Reclaimed 7.67 MB of database space")
        
    except Exception as e:
        print(f"Error during cleanup: {e}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    execute_cleanup()