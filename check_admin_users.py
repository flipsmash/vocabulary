#!/usr/bin/env python3
"""
Check admin users in the database
"""

import mysql.connector
from core.config import get_db_config

def check_admin_users():
    """Check what admin users exist"""
    config = get_db_config()
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT username, email, role, is_active, created_at 
            FROM vocab.users 
            WHERE role = 'admin' OR username = 'admin'
            ORDER BY created_at
        """)
        
        users = cursor.fetchall()
        
        if users:
            print("Admin users found:")
            for username, email, role, is_active, created_at in users:
                status = "Active" if is_active else "Inactive"
                print(f"  Username: {username}, Email: {email}, Role: {role}, Status: {status}, Created: {created_at}")
        else:
            print("No admin users found")
            
        return users
        
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    check_admin_users()