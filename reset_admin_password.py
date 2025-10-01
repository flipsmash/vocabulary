#!/usr/bin/env python3
"""
Reset admin password for testing
"""

import mysql.connector
from core.config import get_db_config
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def reset_admin_password():
    """Reset admin password to 'admin123'"""
    config = get_db_config()
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor()
    
    try:
        # Hash the new password
        new_password = "admin123"
        hashed_password = pwd_context.hash(new_password)
        
        # Update the admin user
        cursor.execute("""
            UPDATE users 
            SET password_hash = %s 
            WHERE username = 'admin'
        """, (hashed_password,))
        
        conn.commit()
        
        if cursor.rowcount > 0:
            print(f"Successfully reset admin password to '{new_password}'")
        else:
            print("No admin user found to update")
            
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    reset_admin_password()