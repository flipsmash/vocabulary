#!/usr/bin/env python3
"""
Manual database cleanup execution
"""

import mysql.connector
from config import get_db_config

def manual_cleanup():
    try:
        db_config = get_db_config()
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Disable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        
        # Drop tables one by one
        tables_to_drop = [
            'word_domains',
            'candidate_observations', 
            'candidate_metrics',
            'definition_candidates',
            'candidate_review_queue'
        ]
        
        print("Manually removing unused tables...")
        
        for table in tables_to_drop:
            try:
                print(f"Dropping {table}...")
                cursor.execute(f"DROP TABLE IF EXISTS {table}")
                print(f"  SUCCESS: {table} dropped")
            except Exception as e:
                print(f"  ERROR dropping {table}: {e}")
        
        # Re-enable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        
        conn.commit()
        
        # Verify removal
        print("\nVerifying removal...")
        for table in tables_to_drop:
            cursor.execute(f"""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = 'vocab' AND table_name = '{table}'
            """)
            exists = cursor.fetchone()[0]
            if exists == 0:
                print(f"  CONFIRMED: {table} successfully removed")
            else:
                print(f"  WARNING: {table} still exists")
        
        # Get final table count
        cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'vocab'")
        final_count = cursor.fetchone()[0]
        
        print(f"\nFinal database contains {final_count} tables")
        print("Manual cleanup completed!")
        
    except Exception as e:
        print(f"Error during manual cleanup: {e}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    manual_cleanup()