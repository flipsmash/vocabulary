#!/usr/bin/env python3
"""
Centralized Configuration Management for Vocabulary System
Manages database connections, paths, and system settings
"""

import os
from typing import Dict, Optional
from pathlib import Path

class VocabularyConfig:
    """Centralized configuration for the vocabulary system"""
    
    # Database Configuration
    DATABASE = {
        'host': '10.0.0.160',
        'port': 3306,
        'database': 'vocab',
        'user': 'brian',
        'password': 'Fl1p5ma5h!'
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
        return cls.DATABASE.copy()
    
    @classmethod
    def get_db_url(cls) -> str:
        """Get database URL for connection strings"""
        return f"mysql://{cls.DATABASE['user']}:{cls.DATABASE['password']}@{cls.DATABASE['host']}:{cls.DATABASE['port']}/{cls.DATABASE['database']}"
    
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
    return config.get_db_config()

def get_database_config():
    """Get database configuration (legacy compatibility)"""
    return config.get_db_config()

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