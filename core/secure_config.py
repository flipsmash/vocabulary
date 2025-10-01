#!/usr/bin/env python3
"""
Secure Configuration Management for Vocabulary System
Supports environment variables, multiple environments, and secure credential handling
"""

import os
import json
import logging
from typing import Dict, Optional, Any
from pathlib import Path
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """Database configuration with validation"""
    host: str
    port: int
    database: str
    user: str
    password: str
    schema: str = 'public'
    pool_size: int = 10
    timeout: int = 30

    def __post_init__(self):
        """Validate configuration after initialization"""
        if not self.host:
            raise ValueError("Database host is required")
        if not self.user:
            raise ValueError("Database user is required")
        if not self.password:
            raise ValueError("Database password is required")
        if not (1 <= self.port <= 65535):
            raise ValueError("Database port must be between 1 and 65535")

    def to_dict(self, include_password: bool = True) -> Dict[str, Any]:
        """Convert to dictionary for psycopg.connect"""
        config = {
            'host': self.host,
            'port': self.port,
            'dbname': self.database,
            'user': self.user,
        }
        if include_password:
            config['password'] = self.password
        if self.schema:
            config['options'] = f'-c search_path={self.schema}'
        return config

    def get_connection_string(self, hide_password: bool = True) -> str:
        """Get connection string representation"""
        password = "***" if hide_password else self.password
        conninfo = (
            f"postgresql://{self.user}:{password}@{self.host}:{self.port}/{self.database}"
        )
        if self.schema:
            conninfo += f"?options=-c%20search_path%3D{self.schema}"
        return conninfo


class SecureConfigManager:
    """Secure configuration manager with environment variable support"""

    def __init__(self):
        self._db_config: Optional[DatabaseConfig] = None
        self._config_file = Path(__file__).parent / 'config.json'
        self._env_file = Path(__file__).parent / '.env'

    def get_database_config(self) -> DatabaseConfig:
        """
        Get database configuration from multiple sources in priority order:
        1. Environment variables
        2. config.json file
        3. Default hardcoded values (development only)
        """
        if self._db_config is None:
            self._db_config = self._load_database_config()

        return self._db_config

    def _load_database_config(self) -> DatabaseConfig:
        """Load database configuration from available sources"""

        # Priority 1: Environment variables
        if self._has_env_config():
            logger.info("Loading database config from environment variables")
            return self._load_from_environment()

        # Priority 2: Configuration file
        if self._config_file.exists():
            logger.info(f"Loading database config from {self._config_file}")
            return self._load_from_file()

        # Priority 3: Default configuration (development/fallback)
        logger.warning("Using default database configuration - not recommended for production")
        return self._load_default_config()

    def _has_env_config(self) -> bool:
        """Check if required environment variables are set"""
        required_vars = ['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']
        return all(os.getenv(var) for var in required_vars)

    def _load_from_environment(self) -> DatabaseConfig:
        """Load configuration from environment variables"""
        return DatabaseConfig(
            host=os.getenv('DB_HOST', '10.0.0.99'),
            port=int(os.getenv('DB_PORT', '6543')),
            database=os.getenv('DB_NAME', 'postgres'),
            user=os.getenv('DB_USER', 'postgres.your-tenant-id'),
            password=os.getenv('DB_PASSWORD', ''),
            schema=os.getenv('DB_SCHEMA', 'vocab'),
            pool_size=int(os.getenv('DB_POOL_SIZE', '10')),
            timeout=int(os.getenv('DB_TIMEOUT', '30'))
        )

    def _load_from_file(self) -> DatabaseConfig:
        """Load configuration from JSON file"""
        try:
            with open(self._config_file, 'r') as f:
                config_data = json.load(f)

            db_data = config_data.get('database', {})
            return DatabaseConfig(**db_data)

        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            return self._load_default_config()

    def _load_default_config(self) -> DatabaseConfig:
        """Load default configuration (fallback)"""
        return DatabaseConfig(
            host='10.0.0.99',
            port=6543,
            database='postgres',
            user='postgres.your-tenant-id',
            password='your-super-secret-and-long-postgres-password',
            schema='vocab',
            pool_size=10,
            timeout=30
        )

    def save_config_template(self) -> str:
        """Create a configuration file template"""
        template = {
            "database": {
                "host": "10.0.0.160",
                "port": 3306,
                "database": "vocab",
                "user": "brian",
                "password": "YOUR_PASSWORD_HERE",
                "charset": "utf8mb4",
                "pool_size": 10,
                "timeout": 30
            },
            "application": {
                "environment": "development",
                "debug": True,
                "log_level": "INFO"
            }
        }

        template_file = self._config_file.parent / 'config.template.json'
        with open(template_file, 'w') as f:
            json.dump(template, f, indent=2)

        return str(template_file)

    def save_env_template(self) -> str:
        """Create an environment file template"""
        env_template = """# Database Configuration
DB_HOST=10.0.0.160
DB_PORT=3306
DB_NAME=vocab
DB_USER=brian
DB_PASSWORD=your_password_here
DB_CHARSET=utf8mb4
DB_POOL_SIZE=10
DB_TIMEOUT=30

# Application Configuration
APP_ENV=development
APP_DEBUG=true
APP_LOG_LEVEL=INFO
"""

        env_template_file = self._config_file.parent / '.env.template'
        with open(env_template_file, 'w') as f:
            f.write(env_template)

        return str(env_template_file)

    def test_database_connection(self) -> bool:
        """Test database connectivity"""
        try:
            import mysql.connector
            config = self.get_database_config()

            with mysql.connector.connect(**config.to_dict()) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                return result[0] == 1

        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    def get_config_info(self) -> Dict[str, Any]:
        """Get configuration information (without sensitive data)"""
        config = self.get_database_config()

        return {
            'database': {
                'host': config.host,
                'port': config.port,
                'database': config.database,
                'user': config.user,
                'connection_string': config.get_connection_string(hide_password=True),
                'pool_size': config.pool_size,
                'timeout': config.timeout
            },
            'config_sources': {
                'env_variables': self._has_env_config(),
                'config_file': self._config_file.exists(),
                'default_fallback': not self._has_env_config() and not self._config_file.exists()
            }
        }


# Global configuration manager instance
config_manager = SecureConfigManager()


def get_db_config() -> Dict[str, Any]:
    """
    Get database configuration as dictionary (legacy compatibility)

    Returns:
        Dictionary suitable for mysql.connector.connect()
    """
    return config_manager.get_database_config().to_dict()


def get_database_config() -> DatabaseConfig:
    """
    Get database configuration as structured object

    Returns:
        DatabaseConfig object with validation and methods
    """
    return config_manager.get_database_config()


def test_database_connection() -> bool:
    """Test database connection"""
    return config_manager.test_database_connection()


def main():
    """Test and display configuration"""
    print("Secure Configuration Manager")
    print("=" * 40)

    # Test configuration loading
    config = get_database_config()
    print(f"Database: {config.get_connection_string()}")

    # Test connection
    if test_database_connection():
        print("[OK] Database connection successful")
    else:
        print("[ERROR] Database connection failed")

    # Display configuration info
    info = config_manager.get_config_info()
    print(f"\nConfiguration Sources:")
    for source, active in info['config_sources'].items():
        status = "[OK]" if active else "[--]"
        print(f"  {status} {source.replace('_', ' ').title()}")

    # Create templates
    print(f"\nCreating configuration templates...")
    config_template = config_manager.save_config_template()
    env_template = config_manager.save_env_template()
    print(f"  Config template: {config_template}")
    print(f"  Environment template: {env_template}")


if __name__ == "__main__":
    main()
