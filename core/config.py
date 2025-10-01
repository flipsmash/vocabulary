#!/usr/bin/env python3
"""
Centralized Configuration Management for Vocabulary System
Manages database connections, paths, and system settings
"""

import os
from typing import Dict, Optional
from pathlib import Path

from .secure_config import get_database_config as secure_get_database_config

class VocabularyConfig:
    """Centralized configuration for the vocabulary system"""

    # Database Configuration
    DATABASE = {
        'host': '10.0.0.99',
        'port': 6543,
        'database': 'postgres',
        'user': 'postgres.your-tenant-id',
        'password': 'your-super-secret-and-long-postgres-password',
        'schema': 'vocab'
    }
    
    # File Paths
    BASE_DIR = Path(__file__).parent
    PHONETIC_CACHE_FILE = BASE_DIR / "phonetic_cache.pkl"
    LOG_FILE = BASE_DIR / "pronunciation_similarity.log"
    
    # Processing Settings
    DEFAULT_BATCH_SIZE = 1000
    DEFAULT_SIMILARITY_THRESHOLD = 0.1
    
    # High-Performance Inserter Settings
    HP_INSERTER = {
        'pool_size': 12,
        'batch_size': 50000,
        'queue_size': 5000000,
        'timeout': 10.0
    }
    
    # CUDA Settings
    CUDA_BATCH_SIZE = 5000

    # Ingestion Defaults (narrow, research/AI-biased)
    INGESTION = {
        'rss_feeds': [
            "https://www.nature.com/subjects/artificial-intelligence.rss",
            "https://www.nature.com/nature/articles?type=news-and-views.rss",
            "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml",
            "https://www.technologyreview.com/feed/",
        ],
        'arxiv_categories': ["cs.CL", "cs.LG", "cs.AI", "stat.ML", "eess.AS"],
        'github_repos': [
            "tensorflow/tensorflow",
            "pytorch/pytorch",
            "huggingface/transformers",
            "scikit-learn/scikit-learn",
            "openai/whisper",
        ],
        # Zipf >= threshold is considered common and filtered out
        'zipf_common_threshold': 2.2,
    }
    
    # Logging Configuration
    LOGGING = {
        'level': 'INFO',
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'file_handler': True,
        'console_handler': True
    }
    
    @classmethod
    def get_db_config(cls) -> Dict:
        """Get database configuration"""
        return secure_get_database_config().to_dict()

    @classmethod
    def get_db_url(cls) -> str:
        """Get database URL for connection strings"""
        db_conf = secure_get_database_config()
        schema_fragment = ''
        if db_conf.schema:
            schema_fragment = f"?options=-c%20search_path%3D{db_conf.schema}"
        password = db_conf.password
        return (
            f"postgresql://{db_conf.user}:{password}@{db_conf.host}:{db_conf.port}/{db_conf.database}"
            f"{schema_fragment}"
        )

    # Ingestion helpers with env-var overrides ---------------------------------
    @classmethod
    def get_rss_feeds(cls) -> list[str]:
        env_list = os.getenv('RSS_FEEDS')
        if env_list:
            feeds = [f.strip() for f in env_list.split(',') if f.strip()]
            if feeds:
                return feeds
        return list(cls.INGESTION.get('rss_feeds', []))

    @classmethod
    def get_arxiv_categories(cls) -> list[str]:
        env_list = os.getenv('ARXIV_CATEGORIES')
        if env_list:
            cats = [c.strip() for c in env_list.split(',') if c.strip()]
            if cats:
                return cats
        return list(cls.INGESTION.get('arxiv_categories', []))

    @classmethod
    def get_github_repos(cls) -> list[str]:
        env_list = os.getenv('GITHUB_REPOS')
        if env_list:
            repos = [r.strip() for r in env_list.split(',') if r.strip()]
            if repos:
                return repos
        return list(cls.INGESTION.get('github_repos', []))

    @classmethod
    def get_zipf_threshold(cls) -> float:
        env = os.getenv('ZIPF_COMMON_THRESHOLD')
        if env:
            try:
                return float(env)
            except ValueError:
                pass
        return float(cls.INGESTION.get('zipf_common_threshold', 3.0))
    
    @classmethod
    def from_env(cls) -> 'VocabularyConfig':
        """Create configuration from environment variables"""
        config = cls()
        
        # Override database settings from environment
        if os.getenv('DB_HOST'):
            cls.DATABASE['host'] = os.getenv('DB_HOST')
        if os.getenv('DB_PORT'):
            cls.DATABASE['port'] = int(os.getenv('DB_PORT'))
        if os.getenv('DB_NAME'):
            cls.DATABASE['database'] = os.getenv('DB_NAME')
        if os.getenv('DB_USER'):
            cls.DATABASE['user'] = os.getenv('DB_USER')
        if os.getenv('DB_PASSWORD'):
            cls.DATABASE['password'] = os.getenv('DB_PASSWORD')
        
        return config
    
    @classmethod
    def update_database(cls, host=None, port=None, database=None, user=None, password=None):
        """Update database configuration"""
        if host is not None:
            cls.DATABASE['host'] = host
        if port is not None:
            cls.DATABASE['port'] = port
        if database is not None:
            cls.DATABASE['database'] = database
        if user is not None:
            cls.DATABASE['user'] = user
        if password is not None:
            cls.DATABASE['password'] = password

# Global configuration instance
config = VocabularyConfig()

# Legacy compatibility - functions that other modules expect
def get_db_config():
    """Get database configuration (legacy compatibility)"""
    return secure_get_database_config().to_dict()

def get_database_config():
    """Get database configuration (legacy compatibility)"""
    return secure_get_database_config()

# Configuration validation
def validate_config():
    """Validate configuration settings"""
    errors = []
    
    # Check database configuration
    required_db_keys = ['host', 'port', 'database', 'user', 'password']
    for key in required_db_keys:
        if not config.DATABASE.get(key):
            errors.append(f"Missing database configuration: {key}")
    
    # Check file paths
    if not config.BASE_DIR.exists():
        errors.append(f"Base directory does not exist: {config.BASE_DIR}")
    
    if errors:
        raise ValueError(f"Configuration validation failed: {', '.join(errors)}")
    
    return True

if __name__ == "__main__":
    # Test configuration
    print("Vocabulary System Configuration")
    print("=" * 50)
    print(f"Database Host: {config.DATABASE['host']}")
    print(f"Database Port: {config.DATABASE['port']}")
    print(f"Database Name: {config.DATABASE['database']}")
    print(f"Database User: {config.DATABASE['user']}")
    print(f"Base Directory: {config.BASE_DIR}")
    print(f"Log File: {config.LOG_FILE}")
    
    try:
        validate_config()
        print("\n[OK] Configuration validation passed")
    except ValueError as e:
        print(f"\n[ERROR] Configuration validation failed: {e}")
