#!/usr/bin/env python3
"""
Check recent harvesting sessions
"""

import mysql.connector
from config import get_db_config

def check_recent_sessions():
    try:
        db_config = get_db_config()
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        print("Recent harvesting sessions:")
        print("=" * 60)
        
        cursor.execute("""
            SELECT * FROM harvesting_sessions 
            ORDER BY session_start DESC 
            LIMIT 5
        """)
        
        sessions = cursor.fetchall()
        
        for session in sessions:
            print(f"ID: {session['id']}")
            print(f"Source: {session['source_type']}")
            print(f"Started: {session['session_start']}")
            print(f"Ended: {session['session_end']}")
            print(f"Status: {session['status']}")
            print(f"Processed: {session['total_processed']}")
            print(f"Found: {session['candidates_found']}")
            print(f"Accepted: {session['candidates_accepted']}")
            if session['notes']:
                print(f"Notes: {session['notes'][:100]}...")
            print("-" * 40)
            
        # Check harvester_config entries
        print("\nHarvester config entries:")
        cursor.execute("""
            SELECT source_type, config_key, config_value 
            FROM harvester_config 
            ORDER BY source_type, config_key
        """)
        
        configs = cursor.fetchall()
        current_source = None
        
        for config in configs:
            if config['source_type'] != current_source:
                current_source = config['source_type']
                print(f"\n{current_source.upper()}:")
            print(f"  {config['config_key']}: {config['config_value']}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    check_recent_sessions()