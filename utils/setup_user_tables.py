#!/usr/bin/env python3
"""
Setup script to create user tables in the database
Run this once to initialize the user management system
"""

import mysql.connector
from config import get_db_config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_user_tables():
    """Create user-related tables in the database"""
    
    # Read the SQL file
    with open('create_user_tables.sql', 'r') as f:
        sql_content = f.read()
    
    # Split into individual statements (basic split on semicolon)
    statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
    
    # Connect to database
    config = get_db_config()
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor()
    
    try:
        logger.info("Setting up user tables...")
        
        for i, statement in enumerate(statements, 1):
            if statement.upper().startswith(('CREATE', 'INSERT', 'USE')):
                logger.info(f"Executing statement {i}: {statement[:50]}...")
                try:
                    cursor.execute(statement)
                    conn.commit()  # Commit each statement individually
                except mysql.connector.Error as e:
                    logger.warning(f"Statement {i} failed: {e}")
                    if "already exists" not in str(e).lower():
                        raise
        
        logger.info("User tables creation completed!")
        
        # Verify the tables were created
        cursor.execute("SHOW TABLES")
        all_tables = cursor.fetchall()
        user_tables = [table[0] for table in all_tables if 'user' in table[0].lower()]
        logger.info(f"User-related tables: {user_tables}")
        
        if user_tables:
            # Check if default admin user was created
            cursor.execute("SELECT username, role FROM users WHERE role = 'admin'")
            admin_users = cursor.fetchall()
            if admin_users:
                logger.info(f"Admin users: {[f'{user[0]} ({user[1]})' for user in admin_users]}")
                logger.info("Default admin login: username='admin', password='admin123'")
            else:
                logger.warning("No admin users found!")
        else:
            logger.warning("No user tables found!")
    
    except mysql.connector.Error as e:
        logger.error(f"Database error: {e}")
        conn.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    setup_user_tables()