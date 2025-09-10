#!/usr/bin/env python3
"""
Final cleanup - remove the last remaining empty table
"""

import mysql.connector
from config import get_db_config

def final_cleanup():
    try:
        db_config = get_db_config()
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        print("Removing final empty table: candidate_review_queue")
        cursor.execute("DROP TABLE IF EXISTS candidate_review_queue")
        conn.commit()
        
        # Verify final state
        cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'vocab'")
        final_count = cursor.fetchone()[0]
        
        print(f"SUCCESS: Database now contains {final_count} clean tables")
        print("Database cleanup completed successfully!")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    final_cleanup()