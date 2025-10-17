#!/usr/bin/env python3
"""
Create a test admin user for quiz testing
"""

from core.database_manager import DatabaseManager
from passlib.context import CryptContext
import sys

def create_test_admin():
    """Create a test admin user with known credentials"""

    db = DatabaseManager()
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    username = "quiz_test_admin"
    password = "quiz_test_123"
    email = "quiz_test@vocab.local"

    try:
        # Check if user already exists
        existing = db.execute_query(
            "SELECT id FROM vocab.users WHERE username = %s",
            (username,)
        )

        if existing:
            print(f"User {username} already exists, updating password...")
            # Update password
            hashed_password = pwd_context.hash(password)
            db.execute_query(
                "UPDATE vocab.users SET password_hash = %s WHERE username = %s",
                (hashed_password, username)
            )
            print(f"✓ Updated password for {username}")
        else:
            # Create new user
            hashed_password = pwd_context.hash(password)
            db.execute_query(
                """INSERT INTO vocab.users (username, email, password_hash, is_admin, is_active)
                   VALUES (%s, %s, %s, 1, 1)""",
                (username, email, hashed_password)
            )
            print(f"✓ Created new admin user: {username}")

        print(f"Credentials for testing:")
        print(f"  Username: {username}")
        print(f"  Password: {password}")
        print(f"  Email: {email}")

        return username, password

    except Exception as e:
        print(f"❌ Error creating test admin: {e}")
        import traceback
        traceback.print_exc()
        return None, None

if __name__ == "__main__":
    create_test_admin()