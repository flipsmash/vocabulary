#!/usr/bin/env python3
"""
Supabase Configuration for Vocabulary System
Updated configuration to use PostgreSQL/Supabase instead of MySQL
"""

import os
from typing import Dict, Optional
from pathlib import Path

class VocabularyConfig:
    """Centralized configuration for the vocabulary system with Supabase support"""
    
    # Supabase/PostgreSQL Database Configuration
    DATABASE = {
        'host': 'localhost',
        'port': 5432,
        'database': 'postgres',
        'user': 'postgres',
        'password': os.getenv('SUPABASE_DB_PASSWORD', 'your-password-here')
    }
    
    # Supabase API Configuration
    SUPABASE = {
        'url': os.getenv('SUPABASE_URL', 'http://localhost:8000'),
        'anon_key': os.getenv('SUPABASE_ANON_KEY', 'your-anon-key-here'),
        'service_role_key': os.getenv('SUPABASE_SERVICE_ROLE_KEY', 'your-service-role-key-here')
    }
    
    # File Paths
    BASE_DIR = Path(__file__).parent
    PHONETIC_CACHE_FILE = BASE_DIR / "phonetic_cache.pkl"
    LOG_FILE = BASE_DIR / "pronunciation_similarity.log"
    
    # Processing Settings (unchanged)
    DEFAULT_BATCH_SIZE = 1000
    DEFAULT_SIMILARITY_THRESHOLD = 0.1
    
    # High-Performance Inserter Settings (PostgreSQL optimized)
    HP_INSERTER = {
        'pool_size': 12,
        'batch_size': 50000,  # PostgreSQL handles larger batches better
        'queue_size': 5000000,
        'timeout': 10.0
    }
    
    # CUDA Settings (unchanged)
    CUDA_BATCH_SIZE = 5000

    # PostgreSQL Connection Pool Settings
    CONNECTION_POOL = {
        'min_connections': 5,
        'max_connections': 20,
        'connection_lifetime': 300,  # 5 minutes
        'connection_idle_timeout': 60  # 1 minute
    }

    # Authentication Settings (for transition period)
    AUTH = {
        'use_supabase_auth': True,  # Set to False during transition
        'jwt_secret': os.getenv('JWT_SECRET', 'your-jwt-secret-here'),
        'session_timeout': 3600  # 1 hour
    }

    # Ingestion Defaults (unchanged)
    INGESTION = {
        'rss_feeds': [
            "https://www.nature.com/subjects/artificial-intelligence.rss",
            "https://www.nature.com/nature/articles?type=news-and-views.rss",
            "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml",
            "https://www.technologyreview.com/feed/",
        ],
        'max_articles_per_feed': 100,
        'processing_batch_size': 50,
        'candidate_score_threshold': 0.6,
        'ngram_max_length': 3,
    }

    @classmethod
    def get_db_config(cls) -> Dict:
        """Get database configuration for PostgreSQL/Supabase"""
        return cls.DATABASE.copy()
    
    @classmethod
    def get_supabase_config(cls) -> Dict:
        """Get Supabase API configuration"""
        return cls.SUPABASE.copy()
    
    @classmethod
    def from_env(cls):
        """Load configuration from environment variables"""
        # Database configuration from environment
        if os.getenv('DATABASE_URL'):
            # Parse DATABASE_URL format: postgresql://user:pass@host:port/db
            import urllib.parse
            result = urllib.parse.urlparse(os.getenv('DATABASE_URL'))
            cls.DATABASE = {
                'host': result.hostname,
                'port': result.port or 5432,
                'database': result.path[1:],  # Remove leading /
                'user': result.username,
                'password': result.password
            }
        
        # Override individual components if set
        cls.DATABASE['host'] = os.getenv('DB_HOST', cls.DATABASE['host'])
        cls.DATABASE['port'] = int(os.getenv('DB_PORT', cls.DATABASE['port']))
        cls.DATABASE['database'] = os.getenv('DB_NAME', cls.DATABASE['database'])
        cls.DATABASE['user'] = os.getenv('DB_USER', cls.DATABASE['user'])
        cls.DATABASE['password'] = os.getenv('DB_PASSWORD', cls.DATABASE['password'])
        
        # Supabase configuration
        cls.SUPABASE['url'] = os.getenv('SUPABASE_URL', cls.SUPABASE['url'])
        cls.SUPABASE['anon_key'] = os.getenv('SUPABASE_ANON_KEY', cls.SUPABASE['anon_key'])
        cls.SUPABASE['service_role_key'] = os.getenv('SUPABASE_SERVICE_ROLE_KEY', cls.SUPABASE['service_role_key'])
        
        return cls
    
    @classmethod
    def get_connection_string(cls) -> str:
        """Get PostgreSQL connection string"""
        config = cls.get_db_config()
        return f"postgresql://{config['user']}:{config['password']}@{config['host']}:{config['port']}/{config['database']}"


# Backward compatibility functions for existing code
def get_db_config():
    """Legacy compatibility function"""
    return VocabularyConfig.get_db_config()

def get_connection():
    """Get PostgreSQL connection (replaces MySQL connection)"""
    import psycopg2
    return psycopg2.connect(**VocabularyConfig.get_db_config())

# Load configuration from environment on import
config = VocabularyConfig.from_env()

# Test connection function
def test_connection():
    """Test database connection"""
    try:
        import psycopg2
        conn = psycopg2.connect(**config.get_db_config())
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        print(f"✅ PostgreSQL connection successful!")
        print(f"Server version: {version}")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

if __name__ == "__main__":
    print("Supabase Configuration Test")
    print("=" * 40)
    
    config_dict = config.get_db_config()
    print(f"Host: {config_dict['host']}")
    print(f"Port: {config_dict['port']}")
    print(f"Database: {config_dict['database']}")
    print(f"User: {config_dict['user']}")
    print(f"Password: {'*' * len(config_dict['password'])}")
    print()
    
    supabase_config = config.get_supabase_config()
    print(f"Supabase URL: {supabase_config['url']}")
    print(f"Anon Key: {supabase_config['anon_key'][:20]}...")
    print()
    
    print("Testing connection...")
    test_connection()