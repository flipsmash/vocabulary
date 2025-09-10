#!/usr/bin/env python3
"""
Fix Progress Tracker Database Schema Issues
Addresses the status column truncation error
"""

import mysql.connector
from config import get_db_config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_and_fix_harvesting_sessions_table():
    """Check and fix the harvesting_sessions table schema"""
    try:
        db_config = get_db_config()
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Check current schema
        cursor.execute("DESCRIBE harvesting_sessions")
        columns = cursor.fetchall()
        
        print("Current harvesting_sessions table schema:")
        for col in columns:
            print(f"  {col[0]}: {col[1]} {col[2]} {col[3]} {col[4]} {col[5]}")
        
        # Check if status column is too small
        status_column = next((col for col in columns if col[0] == 'status'), None)
        
        if status_column:
            column_type = status_column[1].lower()
            print(f"\nCurrent status column type: {column_type}")
            
            # Fix ENUM to include all needed status values
            if 'enum' in column_type:
                logger.info("Expanding ENUM status column to include all needed values")
                cursor.execute("""
                    ALTER TABLE harvesting_sessions 
                    MODIFY COLUMN status ENUM(
                        'running', 'completed', 'failed', 'active', 'paused', 'error', 'unknown'
                    ) DEFAULT 'running'
                """)
                conn.commit()
                logger.info("Successfully expanded status ENUM")
            elif 'varchar' in column_type and ('(' not in column_type or 
                int(column_type.split('(')[1].split(')')[0]) < 20):
                
                logger.info("Status column is too small, expanding to VARCHAR(50)")
                cursor.execute("ALTER TABLE harvesting_sessions MODIFY COLUMN status VARCHAR(50)")
                conn.commit()
                logger.info("Successfully expanded status column")
            else:
                logger.info("Status column size is adequate")
        
        # Check if categories_processed column exists and fix its type
        categories_column = next((col for col in columns if col[0] == 'categories_processed'), None)
        if categories_column:
            column_type = categories_column[1].lower()
            if 'text' not in column_type and 'json' not in column_type:
                logger.info("Fixing categories_processed column type to TEXT")
                cursor.execute("ALTER TABLE harvesting_sessions MODIFY COLUMN categories_processed TEXT")
                conn.commit()
                logger.info("Successfully fixed categories_processed column")
        
        return True
        
    except Exception as e:
        logger.error(f"Error fixing harvesting_sessions table: {e}")
        return False
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

def check_and_create_harvester_config_table():
    """Ensure harvester_config table exists with proper schema"""
    try:
        db_config = get_db_config()
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Check if harvester_config table exists
        cursor.execute("SHOW TABLES LIKE 'harvester_config'")
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            logger.info("Creating harvester_config table")
            cursor.execute("""
                CREATE TABLE harvester_config (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    source_type VARCHAR(50) NOT NULL,
                    config_key VARCHAR(100) NOT NULL,
                    config_value TEXT,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_source_config (source_type, config_key)
                )
            """)
            conn.commit()
            logger.info("Successfully created harvester_config table")
        else:
            logger.info("harvester_config table already exists")
        
        return True
        
    except Exception as e:
        logger.error(f"Error with harvester_config table: {e}")
        return False
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

def test_progress_tracker():
    """Test the progress tracker after fixes"""
    try:
        from progress_tracker import ProgressTracker
        
        tracker = ProgressTracker()
        
        # Test starting a session
        session_id = tracker.start_session('test_source')
        if session_id:
            logger.info(f"Successfully started test session: {session_id}")
            
            # Test updating session
            success = tracker.update_session(session_id, processed=5, candidates_found=3)
            if success:
                logger.info("Successfully updated test session")
            
            # Test ending session
            success = tracker.end_session(session_id, 'completed')
            if success:
                logger.info("Successfully ended test session")
                
            return True
        else:
            logger.error("Failed to start test session")
            return False
            
    except Exception as e:
        logger.error(f"Error testing progress tracker: {e}")
        return False

def main():
    """Main function to fix all schema issues"""
    print("Fixing Progress Tracker Database Schema Issues")
    print("=" * 60)
    
    # Fix harvesting_sessions table
    success1 = check_and_fix_harvesting_sessions_table()
    print()
    
    # Ensure harvester_config table exists
    success2 = check_and_create_harvester_config_table()
    print()
    
    # Test the fixes
    if success1 and success2:
        print("Testing Progress Tracker...")
        success3 = test_progress_tracker()
        
        if success3:
            print("\nSUCCESS: All schema fixes completed successfully!")
            print("The progress tracker should now work without errors.")
        else:
            print("\nWARNING: Schema fixes completed but testing failed.")
            print("Manual investigation may be needed.")
    else:
        print("\nERROR: Some schema fixes failed.")
        print("Please check the error messages above.")

if __name__ == "__main__":
    main()