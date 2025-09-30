#!/usr/bin/env python3
"""
Setup script to create candidate harvesting database schema
"""

import mysql.connector
from mysql.connector import Error
from config import get_db_config

def setup_harvesting_schema():
    """Create the candidate harvesting database schema"""
    
    # Read the SQL file
    try:
        with open('create_candidate_harvesting_schema.sql', 'r', encoding='utf-8') as f:
            schema_sql = f.read()
    except FileNotFoundError:
        print("Error: create_candidate_harvesting_schema.sql not found")
        return False
    
    # Split into individual statements
    statements = [stmt.strip() for stmt in schema_sql.split(';') if stmt.strip()]
    
    try:
        # Connect to database
        db_config = get_db_config()
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        print("Creating candidate harvesting schema...")
        
        # Execute each statement
        for i, statement in enumerate(statements):
            if not statement:
                continue
                
            try:
                cursor.execute(statement)
                print(f"[OK] Executed statement {i+1}/{len(statements)}")
            except Error as e:
                print(f"Warning on statement {i+1}: {e}")
                # Continue with other statements
        
        conn.commit()
        print("\n[SUCCESS] Candidate harvesting schema created successfully!")
        
        # Verify tables were created
        cursor.execute("SHOW TABLES LIKE 'candidate_%'")
        tables = cursor.fetchall()
        print(f"\nCreated tables: {[table[0] for table in tables]}")
        
        return True
        
    except Error as e:
        print(f"Database error: {e}")
        return False
        
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            print("Database connection closed.")

def verify_schema():
    """Verify the schema was created correctly"""
    try:
        db_config = get_db_config()
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Check candidate_words table
        cursor.execute("DESCRIBE candidate_words")
        columns = cursor.fetchall()
        print(f"\ncandidate_words table has {len(columns)} columns:")
        for col in columns[:5]:  # Show first 5 columns
            print(f"  - {col[0]} ({col[1]})")
        
        # Check harvester_config table
        cursor.execute("SELECT COUNT(*) FROM harvester_config")
        config_count = cursor.fetchone()[0]
        print(f"\nharvester_config has {config_count} configuration entries")
        
        # Show some config values
        cursor.execute("SELECT source_type, config_key, config_value FROM harvester_config LIMIT 5")
        configs = cursor.fetchall()
        print("\nSample configuration entries:")
        for source, key, value in configs:
            print(f"  - {source}.{key}: {value[:50]}{'...' if len(value) > 50 else ''}")
        
        return True
        
    except Error as e:
        print(f"Verification error: {e}")
        return False
        
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    print("Setting up Wiktionary Harvester Database Schema")
    print("=" * 50)
    
    if setup_harvesting_schema():
        verify_schema()
    else:
        print("[FAILED] Schema setup failed")