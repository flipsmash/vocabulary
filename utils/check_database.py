#!/usr/bin/env python3
"""
Check what databases are available on the new MySQL server
"""

import mysql.connector
import sys

def check_databases():
    """Check available databases on the new server"""
    try:
        # Connect without specifying a database
        from config import config
        db_config = config.get_db_config()
        conn = mysql.connector.connect(
            host=db_config['host'],
            port=db_config['port'],
            user=db_config['user'],
            password=db_config['password']
        )
        
        cursor = conn.cursor()
        
        print("[OK] Successfully connected to MySQL server at 10.0.0.160")
        
        # Show all databases
        cursor.execute("SHOW DATABASES")
        databases = cursor.fetchall()
        
        print("\n[INFO] Available databases:")
        for (db_name,) in databases:
            print(f"   - {db_name}")
        
        # Check if vocab database exists
        vocab_exists = any(db[0] == 'vocab' for db in databases)
        
        if vocab_exists:
            print("\n[OK] 'vocab' database found!")
            
            # Connect to vocab database and check tables
            conn.close()
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()
            
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            
            print("\n[INFO] Tables in vocab database:")
            for (table_name,) in tables:
                print(f"   - {table_name}")
                
            # Check key tables
            key_tables = ['defined', 'word_phonetics', 'pronunciation_similarity']
            for table in key_tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    print(f"   {table}: {count:,} records")
                except:
                    print(f"   {table}: Table does not exist")
        
        else:
            print("\n[ERROR] 'Vocab' database NOT found!")
            print("\nYou need to either:")
            print("1. Create the 'Vocab' database on the new server")
            print("2. Import your data from the old server")
            print("3. Update the database name in the configuration")
        
        conn.close()
        
    except mysql.connector.Error as err:
        print(f"[ERROR] Database connection error: {err}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    check_databases()