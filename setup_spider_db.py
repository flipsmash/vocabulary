#!/usr/bin/env python3
"""
Create spider database tables
"""

import sys
import os

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.abspath(__file__))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from core.config import get_db_config
import mysql.connector
from mysql.connector import Error

def create_spider_tables():
    """Create spider tracking tables"""
    config = get_db_config()
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor()
    
    try:
        # Spider URL visit tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS spider_visited_urls (
                id INT AUTO_INCREMENT PRIMARY KEY,
                url VARCHAR(2000) NOT NULL,
                url_hash VARCHAR(64) NOT NULL UNIQUE,
                source_type ENUM('wikipedia', 'arxiv', 'gutenberg', 'pubmed', 'news_api') NOT NULL,
                first_visited TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_visited TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                visit_count INT DEFAULT 1,
                success_count INT DEFAULT 0,
                candidates_found INT DEFAULT 0,
                status ENUM('success', 'failed', 'error', 'blocked') DEFAULT 'success',
                
                INDEX idx_url_hash (url_hash),
                INDEX idx_source_visited (source_type, last_visited),
                INDEX idx_expiration (last_visited)
            )
        """)
        
        # Spider session tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS spider_sessions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                session_id VARCHAR(100) NOT NULL UNIQUE,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP NULL,
                total_urls_visited INT DEFAULT 0,
                total_candidates_found INT DEFAULT 0,
                sources_used TEXT,
                session_config TEXT,
                status ENUM('running', 'completed', 'terminated', 'error') DEFAULT 'running',
                
                INDEX idx_session_time (start_time),
                INDEX idx_session_status (status)
            )
        """)
        
        # Source performance tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS spider_source_performance (
                id INT AUTO_INCREMENT PRIMARY KEY,
                source_type ENUM('wikipedia', 'arxiv', 'gutenberg', 'pubmed', 'news_api') NOT NULL,
                date_tracked DATE NOT NULL,
                urls_visited INT DEFAULT 0,
                success_rate DECIMAL(5,2) DEFAULT 0.00,
                avg_candidates_per_url DECIMAL(8,2) DEFAULT 0.00,
                avg_response_time_ms INT DEFAULT 0,
                error_count INT DEFAULT 0,
                
                UNIQUE KEY unique_source_date (source_type, date_tracked),
                INDEX idx_source_performance (source_type, date_tracked)
            )
        """)
        
        conn.commit()
        print("SUCCESS: Spider database tables created successfully!")
        
    except Error as e:
        print(f"ERROR: Error creating spider tables: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    create_spider_tables()