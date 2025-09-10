#!/usr/bin/env python3
"""
Update source_type enum to include new multi-source types
"""

import mysql.connector
from mysql.connector import Error
from config import get_db_config

def update_source_enum():
    """Add new source types to the enum"""
    
    db_config = get_db_config()
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        print("Updating source_type enum to include new source types...")
        
        # Update the enum to include new source types
        cursor.execute("""
            ALTER TABLE candidate_words 
            MODIFY COLUMN source_type ENUM(
                'wiktionary',
                'gutenberg', 
                'arxiv',
                'pubmed',
                'wikipedia',
                'news_api',
                'academic_journals',
                'literary_classics', 
                'historical_documents',
                'multi_source',
                'other'
            ) NOT NULL
        """)
        
        conn.commit()
        print("✅ Successfully updated source_type enum!")
        
        # Verify the change
        cursor.execute("SHOW COLUMNS FROM candidate_words LIKE 'source_type'")
        result = cursor.fetchone()
        
        if result:
            print(f"\nUpdated source_type column: {result[1]}")
        
        print("\n✅ Schema update completed successfully!")
        
    except Error as e:
        print(f"❌ Database error: {e}")
        
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    update_source_enum()