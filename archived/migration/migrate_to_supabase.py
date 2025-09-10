#!/usr/bin/env python3
"""
MySQL to Supabase (PostgreSQL) Migration Script
Migrates vocabulary database with optimized performance for large datasets
"""

import mysql.connector
import psycopg2
import psycopg2.extras
import json
import time
from datetime import datetime
from tqdm import tqdm
import pandas as pd
import logging
from typing import Dict, List, Tuple, Optional
import argparse
import sys
import os

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DatabaseMigrator:
    """Handles migration from MySQL to PostgreSQL/Supabase"""
    
    def __init__(self, mysql_config: Dict, postgres_config: Dict):
        self.mysql_config = mysql_config
        self.postgres_config = postgres_config
        self.mysql_conn = None
        self.postgres_conn = None
        
    def connect_mysql(self):
        """Connect to MySQL source database"""
        try:
            self.mysql_conn = mysql.connector.connect(**self.mysql_config)
            logger.info("Connected to MySQL database")
        except Exception as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            raise
            
    def connect_postgres(self):
        """Connect to PostgreSQL/Supabase target database"""
        try:
            self.postgres_conn = psycopg2.connect(**self.postgres_config)
            self.postgres_conn.autocommit = False
            logger.info("Connected to PostgreSQL database")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise
            
    def create_tables(self):
        """Create PostgreSQL tables with optimized schema"""
        logger.info("Creating PostgreSQL tables...")
        
        tables = {
            'users': '''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    full_name VARCHAR(255),
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('user', 'admin')),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    last_login_at TIMESTAMPTZ NULL
                );
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
            ''',
            
            'defined': '''
                CREATE TABLE IF NOT EXISTS defined (
                    id SERIAL PRIMARY KEY,
                    term VARCHAR(255) NOT NULL,
                    definition TEXT NOT NULL,
                    part_of_speech VARCHAR(50),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_defined_term ON defined(term);
                CREATE INDEX IF NOT EXISTS idx_defined_pos ON defined(part_of_speech);
                -- Full text search index
                CREATE INDEX IF NOT EXISTS idx_definition_fts ON defined 
                USING GIN(to_tsvector('english', definition || ' ' || term));
            ''',
            
            'word_phonetics': '''
                CREATE TABLE IF NOT EXISTS word_phonetics (
                    word_id INTEGER PRIMARY KEY REFERENCES defined(id) ON DELETE CASCADE,
                    word VARCHAR(255) NOT NULL,
                    ipa_transcription TEXT,
                    arpabet_transcription TEXT,
                    phonemes_array TEXT[], -- Enhanced: native array support
                    syllable_count INTEGER,
                    stress_pattern INTEGER[], -- Enhanced: stress as integer array  
                    phonemes_json TEXT, -- Keep for backward compatibility
                    transcription_source VARCHAR(50),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_phonetics_word ON word_phonetics(word);
                CREATE INDEX IF NOT EXISTS idx_phonetics_syllables ON word_phonetics(syllable_count);
                -- GIN index for array operations
                CREATE INDEX IF NOT EXISTS idx_phonemes_gin ON word_phonetics 
                USING GIN(phonemes_array);
            ''',
            
            'pronunciation_similarity': '''
                CREATE TABLE IF NOT EXISTS pronunciation_similarity (
                    word1_id INTEGER,
                    word2_id INTEGER,
                    overall_similarity DECIMAL(6,5),
                    phonetic_distance DECIMAL(6,5),
                    stress_similarity DECIMAL(6,5),
                    rhyme_score DECIMAL(6,5),
                    syllable_similarity DECIMAL(6,5),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (word1_id, word2_id),
                    CONSTRAINT chk_word_order CHECK (word1_id < word2_id),
                    CONSTRAINT fk_word1 FOREIGN KEY (word1_id) REFERENCES defined(id) ON DELETE CASCADE,
                    CONSTRAINT fk_word2 FOREIGN KEY (word2_id) REFERENCES defined(id) ON DELETE CASCADE
                );
                -- Optimized indexes for similarity queries
                CREATE INDEX IF NOT EXISTS idx_overall_similarity ON pronunciation_similarity(overall_similarity DESC);
                CREATE INDEX IF NOT EXISTS idx_word1_similarity ON pronunciation_similarity(word1_id, overall_similarity DESC);
                CREATE INDEX IF NOT EXISTS idx_word2_similarity ON pronunciation_similarity(word2_id, overall_similarity DESC);
                -- Partial index for high similarity (most common queries)
                CREATE INDEX IF NOT EXISTS idx_high_similarity ON pronunciation_similarity(overall_similarity DESC, word1_id, word2_id) 
                WHERE overall_similarity > 0.3;
            ''',
            
            'definition_similarity': '''
                CREATE TABLE IF NOT EXISTS definition_similarity (
                    word1_id INTEGER,
                    word2_id INTEGER,
                    cosine_similarity DECIMAL(6,5),
                    embedding_model VARCHAR(100),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (word1_id, word2_id, embedding_model),
                    CONSTRAINT chk_def_word_order CHECK (word1_id < word2_id),
                    CONSTRAINT fk_def_word1 FOREIGN KEY (word1_id) REFERENCES defined(id) ON DELETE CASCADE,
                    CONSTRAINT fk_def_word2 FOREIGN KEY (word2_id) REFERENCES defined(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_cosine_similarity ON definition_similarity(cosine_similarity DESC);
                CREATE INDEX IF NOT EXISTS idx_def_word1_similarity ON definition_similarity(word1_id, cosine_similarity DESC);
            ''',
            
            'word_domains': '''
                CREATE TABLE IF NOT EXISTS word_domains (
                    word_id INTEGER PRIMARY KEY REFERENCES defined(id) ON DELETE CASCADE,
                    term VARCHAR(255),
                    primary_domain VARCHAR(100),
                    all_domains JSONB, -- Enhanced: JSONB for better performance
                    cluster_id INTEGER,
                    confidence_scores JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_primary_domain ON word_domains(primary_domain);
                CREATE INDEX IF NOT EXISTS idx_cluster_id ON word_domains(cluster_id);
                -- GIN index for JSONB queries
                CREATE INDEX IF NOT EXISTS idx_all_domains_gin ON word_domains USING GIN(all_domains);
            ''',
            
            'word_frequencies_independent': '''
                CREATE TABLE IF NOT EXISTS word_frequencies_independent (
                    word_id INTEGER PRIMARY KEY REFERENCES defined(id) ON DELETE CASCADE,
                    term VARCHAR(255),
                    independent_frequency DECIMAL(10,8),
                    original_frequency DECIMAL(10,8),
                    source_frequencies JSONB,
                    method_count INTEGER,
                    frequency_rank INTEGER,
                    rarity_percentile DECIMAL(5,2),
                    calculation_date TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_independent_frequency ON word_frequencies_independent(independent_frequency DESC);
                CREATE INDEX IF NOT EXISTS idx_frequency_rank ON word_frequencies_independent(frequency_rank);
                CREATE INDEX IF NOT EXISTS idx_rarity_percentile ON word_frequencies_independent(rarity_percentile);
            ''',
            
            'quiz_tables': '''
                CREATE TABLE IF NOT EXISTS user_quiz_results (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    word_id INTEGER NOT NULL REFERENCES defined(id) ON DELETE CASCADE,
                    question_type VARCHAR(20) NOT NULL CHECK (question_type IN ('multiple_choice', 'true_false', 'matching')),
                    is_correct BOOLEAN NOT NULL,
                    response_time_ms INTEGER,
                    answered_at TIMESTAMPTZ DEFAULT NOW(),
                    difficulty_level VARCHAR(20) DEFAULT 'medium' CHECK (difficulty_level IN ('easy', 'medium', 'hard')),
                    session_id VARCHAR(50)
                );
                CREATE INDEX IF NOT EXISTS idx_quiz_user_word ON user_quiz_results(user_id, word_id);
                CREATE INDEX IF NOT EXISTS idx_quiz_user_time ON user_quiz_results(user_id, answered_at);
                CREATE INDEX IF NOT EXISTS idx_quiz_session ON user_quiz_results(session_id);
                
                CREATE TABLE IF NOT EXISTS user_word_mastery (
                    user_id INTEGER NOT NULL,
                    word_id INTEGER NOT NULL REFERENCES defined(id) ON DELETE CASCADE,
                    mastery_level VARCHAR(20) DEFAULT 'learning' CHECK (mastery_level IN ('learning', 'reviewing', 'mastered')),
                    total_attempts INTEGER DEFAULT 0,
                    correct_attempts INTEGER DEFAULT 0,
                    last_seen TIMESTAMPTZ DEFAULT NOW(),
                    next_review TIMESTAMPTZ DEFAULT NOW(),
                    streak INTEGER DEFAULT 0,
                    ease_factor REAL DEFAULT 2.5,
                    PRIMARY KEY (user_id, word_id)
                );
                CREATE INDEX IF NOT EXISTS idx_mastery_next_review ON user_word_mastery(user_id, next_review);
                CREATE INDEX IF NOT EXISTS idx_mastery_level ON user_word_mastery(user_id, mastery_level);
            '''
        }
        
        cursor = self.postgres_conn.cursor()
        for table_name, sql in tables.items():
            try:
                cursor.execute(sql)
                logger.info(f"Created table group: {table_name}")
            except Exception as e:
                logger.error(f"Error creating {table_name}: {e}")
                self.postgres_conn.rollback()
                raise
                
        self.postgres_conn.commit()
        cursor.close()
        logger.info("All tables created successfully")
        
    def migrate_table(self, table_name: str, batch_size: int = 10000) -> int:
        """Migrate a single table with progress tracking"""
        logger.info(f"Starting migration of {table_name}")
        
        mysql_cursor = self.mysql_conn.cursor(dictionary=True)
        postgres_cursor = self.postgres_conn.cursor()
        
        # Get total count
        mysql_cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
        total_count = mysql_cursor.fetchone()['count']
        
        if total_count == 0:
            logger.info(f"Table {table_name} is empty, skipping")
            return 0
            
        logger.info(f"Migrating {total_count:,} records from {table_name}")
        
        # Get column information
        mysql_cursor.execute(f"DESCRIBE {table_name}")
        columns_info = mysql_cursor.fetchall()
        column_names = [col['Field'] for col in columns_info]
        
        migrated_count = 0
        
        # Process in batches
        with tqdm(total=total_count, desc=f"Migrating {table_name}") as pbar:
            for offset in range(0, total_count, batch_size):
                # Fetch batch from MySQL
                mysql_cursor.execute(
                    f"SELECT * FROM {table_name} LIMIT {batch_size} OFFSET {offset}"
                )
                batch_data = mysql_cursor.fetchall()
                
                if not batch_data:
                    break
                    
                # Transform data for PostgreSQL
                transformed_data = self.transform_batch(table_name, batch_data)
                
                # Insert into PostgreSQL
                if transformed_data:
                    self.insert_batch(postgres_cursor, table_name, transformed_data, column_names)
                    migrated_count += len(transformed_data)
                
                pbar.update(len(batch_data))
                
        self.postgres_conn.commit()
        postgres_cursor.close()
        mysql_cursor.close()
        
        logger.info(f"Completed migration of {table_name}: {migrated_count:,} records")
        return migrated_count
        
    def transform_batch(self, table_name: str, batch_data: List[Dict]) -> List[Dict]:
        """Transform MySQL data for PostgreSQL compatibility"""
        transformed = []
        
        for row in batch_data:
            # Convert datetime objects to strings
            for key, value in row.items():
                if isinstance(value, datetime):
                    row[key] = value.isoformat()
                elif value is None:
                    row[key] = None
                    
            # Table-specific transformations
            if table_name == 'word_phonetics':
                # Parse phonemes_json into array format
                if row.get('phonemes_json'):
                    try:
                        phonemes = json.loads(row['phonemes_json'])
                        if isinstance(phonemes, list):
                            row['phonemes_array'] = phonemes
                    except:
                        row['phonemes_array'] = None
                        
                # Parse stress pattern into integer array
                if row.get('stress_pattern'):
                    try:
                        # Extract numbers from stress pattern
                        import re
                        stress_nums = re.findall(r'\d', str(row['stress_pattern']))
                        row['stress_pattern_array'] = [int(x) for x in stress_nums] if stress_nums else None
                    except:
                        row['stress_pattern_array'] = None
                        
            elif table_name in ['word_domains', 'word_frequencies_independent']:
                # Convert JSON strings to proper objects
                for json_col in ['all_domains', 'confidence_scores', 'source_frequencies']:
                    if json_col in row and row[json_col]:
                        try:
                            if isinstance(row[json_col], str):
                                row[json_col] = json.loads(row[json_col])
                        except:
                            row[json_col] = None
                            
            transformed.append(row)
            
        return transformed
        
    def insert_batch(self, cursor, table_name: str, data: List[Dict], column_names: List[str]):
        """Insert batch data using efficient PostgreSQL methods"""
        if not data:
            return
            
        # Prepare data for insertion
        values_list = []
        for row in data:
            values = tuple(row.get(col) for col in column_names)
            values_list.append(values)
            
        # Create placeholders
        placeholders = ','.join(['%s'] * len(column_names))
        columns_str = ','.join(column_names)
        
        # Handle conflicts for tables with primary keys
        conflict_resolution = ""
        if table_name in ['defined', 'users']:
            conflict_resolution = "ON CONFLICT DO NOTHING"
        elif table_name in ['pronunciation_similarity', 'definition_similarity']:
            conflict_resolution = "ON CONFLICT (word1_id, word2_id) DO UPDATE SET overall_similarity = EXCLUDED.overall_similarity"
            
        query = f"""
            INSERT INTO {table_name} ({columns_str}) 
            VALUES ({placeholders}) 
            {conflict_resolution}
        """
        
        try:
            psycopg2.extras.execute_batch(cursor, query, values_list, page_size=1000)
        except Exception as e:
            logger.error(f"Error inserting batch into {table_name}: {e}")
            raise
            
    def run_migration(self, tables: Optional[List[str]] = None) -> Dict[str, int]:
        """Run the complete migration process"""
        migration_order = [
            'users',
            'defined', 
            'word_phonetics',
            'word_domains',
            'word_frequencies_independent',
            'pronunciation_similarity',  # Large table
            'definition_similarity',     # Large table
            'user_quiz_results',
            'user_word_mastery'
        ]
        
        if tables:
            migration_order = [t for t in migration_order if t in tables]
            
        results = {}
        start_time = time.time()
        
        try:
            self.connect_mysql()
            self.connect_postgres()
            self.create_tables()
            
            for table in migration_order:
                if self.table_exists_mysql(table):
                    table_start = time.time()
                    count = self.migrate_table(table, batch_size=50000 if 'similarity' in table else 10000)
                    table_time = time.time() - table_start
                    results[table] = {
                        'count': count,
                        'time_seconds': round(table_time, 2)
                    }
                    logger.info(f"Table {table} migrated in {table_time:.2f} seconds")
                else:
                    logger.warning(f"Table {table} does not exist in MySQL, skipping")
                    
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise
        finally:
            if self.mysql_conn:
                self.mysql_conn.close()
            if self.postgres_conn:
                self.postgres_conn.close()
                
        total_time = time.time() - start_time
        logger.info(f"Migration completed in {total_time:.2f} seconds")
        
        return results
        
    def table_exists_mysql(self, table_name: str) -> bool:
        """Check if table exists in MySQL"""
        cursor = self.mysql_conn.cursor()
        cursor.execute("SHOW TABLES LIKE %s", (table_name,))
        result = cursor.fetchone()
        cursor.close()
        return result is not None

def main():
    parser = argparse.ArgumentParser(description='Migrate MySQL vocabulary database to Supabase')
    parser.add_argument('--mysql-host', default='10.0.0.160', help='MySQL host')
    parser.add_argument('--mysql-port', type=int, default=3306, help='MySQL port')
    parser.add_argument('--mysql-db', default='vocab', help='MySQL database name')
    parser.add_argument('--mysql-user', default='brian', help='MySQL username')
    parser.add_argument('--mysql-password', default='Fl1p5ma5h!', help='MySQL password')
    
    parser.add_argument('--postgres-host', default='localhost', help='PostgreSQL host')
    parser.add_argument('--postgres-port', type=int, default=5432, help='PostgreSQL port')
    parser.add_argument('--postgres-db', default='postgres', help='PostgreSQL database name')
    parser.add_argument('--postgres-user', default='postgres', help='PostgreSQL username')
    parser.add_argument('--postgres-password', required=True, help='PostgreSQL password')
    
    parser.add_argument('--tables', nargs='+', help='Specific tables to migrate')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be migrated')
    
    args = parser.parse_args()
    
    mysql_config = {
        'host': args.mysql_host,
        'port': args.mysql_port,
        'database': args.mysql_db,
        'user': args.mysql_user,
        'password': args.mysql_password
    }
    
    postgres_config = {
        'host': args.postgres_host,
        'port': args.postgres_port,
        'database': args.postgres_db,
        'user': args.postgres_user,
        'password': args.postgres_password
    }
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No data will be migrated")
        logger.info(f"Would migrate from: {args.mysql_host}:{args.mysql_port}/{args.mysql_db}")
        logger.info(f"Would migrate to: {args.postgres_host}:{args.postgres_port}/{args.postgres_db}")
        return
    
    migrator = DatabaseMigrator(mysql_config, postgres_config)
    
    try:
        results = migrator.run_migration(args.tables)
        
        print("\n" + "="*50)
        print("MIGRATION SUMMARY")
        print("="*50)
        
        total_records = 0
        for table, stats in results.items():
            print(f"{table:25} {stats['count']:>10,} records in {stats['time_seconds']:>6.1f}s")
            total_records += stats['count']
            
        print("-"*50)
        print(f"{'TOTAL':25} {total_records:>10,} records")
        print("="*50)
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()