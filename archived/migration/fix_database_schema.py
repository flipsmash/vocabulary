#!/usr/bin/env python3
"""
Fix database schema constraints for multi-source harvester
"""

import mysql.connector
from mysql.connector import Error
from config import get_db_config

def check_and_fix_schema():
    """Check current schema and fix constraints"""
    
    db_config = get_db_config()
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        print("Checking current candidate_words table schema...")
        
        # Check current schema
        cursor.execute("DESCRIBE candidate_words")
        columns = cursor.fetchall()
        
        print("\nCurrent schema:")
        for col in columns:
            print(f"  {col[0]}: {col[1]} {'NULL' if col[2] == 'YES' else 'NOT NULL'} {col[4] if col[4] else ''}")
        
        # Check if source_type column needs expanding
        cursor.execute("SHOW COLUMNS FROM candidate_words LIKE 'source_type'")
        source_type_info = cursor.fetchone()
        
        if source_type_info:
            column_type = source_type_info[1]
            print(f"\nCurrent source_type column: {column_type}")
            
            # If it's too small, expand it
            if 'varchar(3)' in column_type.lower() or 'varchar(5)' in column_type.lower():
                print("Expanding source_type column to VARCHAR(50)...")
                
                cursor.execute("""
                    ALTER TABLE candidate_words 
                    MODIFY COLUMN source_type VARCHAR(50) NOT NULL
                """)
                conn.commit()
                print("✅ Successfully expanded source_type column!")
            
            elif 'varchar' in column_type.lower():
                # Extract length
                import re
                match = re.search(r'varchar\((\d+)\)', column_type.lower())
                if match:
                    length = int(match.group(1))
                    if length < 20:
                        print(f"Expanding source_type column from VARCHAR({length}) to VARCHAR(50)...")
                        
                        cursor.execute("""
                            ALTER TABLE candidate_words 
                            MODIFY COLUMN source_type VARCHAR(50) NOT NULL
                        """)
                        conn.commit()
                        print("✅ Successfully expanded source_type column!")
                    else:
                        print(f"Source_type column is already sufficient: VARCHAR({length})")
                else:
                    print("Could not parse current varchar length, expanding anyway...")
                    cursor.execute("""
                        ALTER TABLE candidate_words 
                        MODIFY COLUMN source_type VARCHAR(50) NOT NULL
                    """)
                    conn.commit()
                    print("✅ Successfully expanded source_type column!")
            else:
                print(f"Source_type column type '{column_type}' doesn't need expansion")
        
        # Also check other potentially problematic columns
        print("\nChecking other columns for potential issues...")
        
        # Check part_of_speech column
        cursor.execute("SHOW COLUMNS FROM candidate_words LIKE 'part_of_speech'")
        pos_info = cursor.fetchone()
        
        if pos_info:
            pos_type = pos_info[1]
            print(f"part_of_speech column: {pos_type}")
            
            if 'varchar' in pos_type.lower():
                match = re.search(r'varchar\((\d+)\)', pos_type.lower())
                if match and int(match.group(1)) < 20:
                    print("Expanding part_of_speech column...")
                    cursor.execute("""
                        ALTER TABLE candidate_words 
                        MODIFY COLUMN part_of_speech VARCHAR(30) NOT NULL
                    """)
                    conn.commit()
                    print("✅ Expanded part_of_speech column!")
        
        print("\n" + "="*50)
        print("Final schema check:")
        cursor.execute("DESCRIBE candidate_words")
        columns = cursor.fetchall()
        
        for col in columns:
            print(f"  {col[0]}: {col[1]} {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
        
        print("\n✅ Schema check and fixes completed!")
        
    except Error as e:
        print(f"❌ Database error: {e}")
        
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    check_and_fix_schema()