#!/usr/bin/env python3
"""Centralized PostgreSQL connection manager with pooling."""

from typing import Optional, Dict, Any, Generator, Union
import logging
from contextlib import contextmanager
from threading import Lock

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from psycopg.pq import TransactionStatus

try:
    from .secure_config import get_database_config
except ImportError:
    from secure_config import get_database_config

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Centralized database connection manager with connection pooling
    Provides consistent database access patterns across the entire application
    """

    _instance: Optional['DatabaseManager'] = None
    _lock = Lock()

    def __new__(cls) -> 'DatabaseManager':
        """Singleton pattern to ensure one database manager instance"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize database manager with connection pool"""
        if hasattr(self, '_initialized'):
            return

        self.config_obj = get_database_config()
        self.config = self.config_obj.to_dict()
        self.pool: Optional[ConnectionPool] = None
        self._initialized = False
        self.setup_connection_pool()

    def setup_connection_pool(self):
        """Setup PostgreSQL connection pool"""
        try:
            conninfo = self.config_obj.get_connection_string(hide_password=False)
            max_size = self.config_obj.pool_size or 10
            self.pool = ConnectionPool(
                conninfo=conninfo,
                min_size=1,
                max_size=max_size,
                timeout=self.config_obj.timeout,
                name="vocabulary_pool",
            )
            self._initialized = True
            logger.info("Database connection pool initialized successfully")

        except Exception as exc:
            logger.error(f"Failed to create PostgreSQL connection pool: {exc}")
            raise

    @contextmanager
    def get_connection(self, dictionary: bool = False, autocommit: bool = False):
        """
        Get a database connection from the pool

        Args:
            dictionary: Whether to return results as dictionaries
            autocommit: Whether to enable autocommit mode

        Yields:
            Database connection

        Example:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM vocab.defined")
                results = cursor.fetchall()
        """
        if not self.pool:
            raise RuntimeError("Database connection pool is not initialized")

        with self.pool.connection() as connection:
            connection.autocommit = autocommit
            try:
                if self.config_obj.schema:
                    connection.execute(
                        f'SET search_path TO "{self.config_obj.schema}"',
                        prepare=False,
                    )
                yield connection
                if not autocommit:
                    connection.commit()
            except Exception:
                if not autocommit:
                    connection.rollback()
                raise
            finally:
                # Only reset autocommit if not in a transaction
                # Check transaction status before attempting to change autocommit
                if connection.info.transaction_status == TransactionStatus.IDLE:
                    connection.autocommit = False

    @contextmanager
    def get_cursor(self, dictionary: bool = False, autocommit: bool = False):
        """
        Get a database cursor (convenience method)

        Args:
            dictionary: Whether to return results as dictionaries
            autocommit: Whether to enable autocommit mode

        Yields:
            Database cursor wrapper that disables prepared statements

        Example:
            with db_manager.get_cursor(dictionary=True) as cursor:
                cursor.execute("SELECT * FROM vocab.defined WHERE id = %s", (123,))
                result = cursor.fetchone()
        """
        cursor_kwargs = {}
        if dictionary:
            cursor_kwargs['row_factory'] = dict_row

        with self.get_connection(dictionary=dictionary, autocommit=autocommit) as conn:
            with conn.cursor(**cursor_kwargs) as real_cursor:
                # Wrap cursor to intercept execute() and disable prepared statements
                yield CursorWrapper(real_cursor)


class CursorWrapper:
    """
    Wrapper around psycopg cursor that disables prepared statements by default.
    Prevents "prepared statement already exists" errors when reusing connections.
    """

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, params=None, **kwargs):
        """Execute with prepare=False by default"""
        kwargs.setdefault('prepare', False)
        return self._cursor.execute(query, params, **kwargs)

    def executemany(self, query, params_seq, **kwargs):
        """Execute many - prepare parameter not supported by psycopg2"""
        # Remove 'prepare' if present, as psycopg2 doesn't support it
        kwargs.pop('prepare', None)
        return self._cursor.executemany(query, params_seq, **kwargs)

    # Delegate all other methods/attributes to the real cursor
    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self._cursor.__exit__(*args)

    def execute_query(self, query: str, params: Optional[tuple] = None,
                     fetch: bool = True, dictionary: bool = False) -> Optional[Any]:
        """
        Execute a single query and return results

        Args:
            query: SQL query to execute
            params: Query parameters
            fetch: Whether to fetch results (False for INSERT/UPDATE/DELETE)
            dictionary: Whether to return results as dictionaries

        Returns:
            Query results or None for non-fetch queries

        Example:
            # Fetch results
            results = db_manager.execute_query(
                "SELECT * FROM vocab.defined WHERE term = %s",
                ("aberrant",),
                dictionary=True
            )

            # Insert/Update (no fetch)
            db_manager.execute_query(
                "UPDATE vocab.defined SET frequency = %s WHERE id = %s",
                (0.5, 123),
                fetch=False
            )
        """
        with self.get_cursor(dictionary=dictionary) as cursor:
            cursor.execute(query, params or ())

            if fetch:
                return cursor.fetchall()
            return cursor.rowcount

    def execute_many(self, query: str, params_list: list,
                    autocommit: bool = False) -> int:
        """
        Execute a query with multiple parameter sets (batch insert/update)

        Args:
            query: SQL query to execute
            params_list: List of parameter tuples
            autocommit: Whether to enable autocommit mode

        Returns:
            Number of affected rows

        Example:
            params = [
                ("word1", "definition1"),
                ("word2", "definition2"),
                ("word3", "definition3")
            ]
            rows_affected = db_manager.execute_many(
                "INSERT INTO vocab.candidate_words (term, raw_definition) VALUES (%s, %s)",
                params
            )
        """
        with self.get_cursor(autocommit=autocommit) as cursor:
            cursor.executemany(query, params_list)
            return cursor.rowcount

    def get_table_count(self, table_name: str) -> int:
        """
        Get the number of rows in a table

        Args:
            table_name: Name of the table

        Returns:
            Number of rows in the table

        Example:
            count = db_manager.get_table_count("defined")
        """
        result = self.execute_query(f"SELECT COUNT(*) FROM {table_name}")
        return result[0][0] if result else 0

    def table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists

        Args:
            table_name: Name of the table to check

        Returns:
            True if table exists, False otherwise
        """
        query = """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """
        result = self.execute_query(query, (self.config['database'], table_name))
        return result[0][0] > 0 if result else False

    def get_connection_info(self) -> Dict[str, Any]:
        """
        Get information about the database connection

        Returns:
            Dictionary with connection information
        """
        info = {
            'host': self.config['host'],
            'port': self.config['port'],
            'database': self.config['database'],
            'user': self.config['user'],
            'pool_size': self.pool.pool_size if self.pool else 0,
            'initialized': self._initialized
        }

        try:
            with self.get_connection() as conn:
                info['connected'] = conn.is_connected()
                info['server_version'] = conn.get_server_info()
        except Exception as e:
            info['connected'] = False
            info['error'] = str(e)

        return info

    def test_connection(self) -> bool:
        """
        Test database connectivity

        Returns:
            True if connection successful, False otherwise
        """
        try:
            with self.get_connection() as conn:
                return conn.is_connected()
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def close_pool(self):
        """Close the connection pool"""
        if self.pool:
            try:
                # Close all connections in the pool
                while True:
                    try:
                        conn = self.pool.get_connection()
                        conn.close()
                    except:
                        break
                self._initialized = False
                logger.info("Database connection pool closed")
            except Exception as e:
                logger.error(f"Error closing connection pool: {e}")


# Global database manager instance
db_manager = DatabaseManager()


def get_database_manager() -> DatabaseManager:
    """
    Get the global database manager instance

    Returns:
        DatabaseManager instance
    """
    return db_manager


# Legacy compatibility functions for existing code
def get_connection():
    """
    Legacy function for backward compatibility

    Returns:
        Raw mysql.connector connection (not recommended for new code)
    """
    logger.warning("Using legacy get_connection(). Consider migrating to DatabaseManager.")
    return mysql.connector.connect(**get_db_config())


# Convenience functions for common patterns
@contextmanager
def database_connection(dictionary: bool = False, autocommit: bool = False):
    """
    Context manager for database connections

    Args:
        dictionary: Whether to return results as dictionaries
        autocommit: Whether to enable autocommit mode

    Yields:
        Database connection

    Example:
        with database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vocab.defined")
            results = cursor.fetchall()
    """
    with db_manager.get_connection(dictionary=dictionary, autocommit=autocommit) as conn:
        yield conn


@contextmanager
def database_cursor(dictionary: bool = False, autocommit: bool = False):
    """
    Context manager for database cursors

    Args:
        dictionary: Whether to return results as dictionaries
        autocommit: Whether to enable autocommit mode

    Yields:
        Database cursor

    Example:
        with database_cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM vocab.defined WHERE id = %s", (123,))
            result = cursor.fetchone()
    """
    with db_manager.get_cursor(dictionary=dictionary, autocommit=autocommit) as cursor:
        yield cursor


def main():
    """Test the database manager"""
    print("Testing Database Manager")
    print("=" * 40)

    # Test connection
    if db_manager.test_connection():
        print("SUCCESS: Database connection successful")
    else:
        print("ERROR: Database connection failed")
        return

    # Get connection info
    info = db_manager.get_connection_info()
    print(f"Database: {info['database']} on {info['host']}:{info['port']}")
    print(f"Server version: {info.get('server_version', 'Unknown')}")
    print(f"Pool size: {info['pool_size']}")

    # Test table counts
    try:
        defined_count = db_manager.get_table_count("defined")
        candidates_count = db_manager.get_table_count("candidate_words")

        print(f"Defined words: {defined_count:,}")
        print(f"Candidate words: {candidates_count:,}")

    except Exception as e:
        print(f"Error getting table counts: {e}")

    # Test query execution
    try:
        sample_words = db_manager.execute_query(
            "SELECT term, part_of_speech FROM vocab.defined LIMIT 3",
            dictionary=True
        )

        print(f"\nSample words:")
        for word in sample_words:
            print(f"  {word['term']} ({word['part_of_speech']})")

    except Exception as e:
        print(f"Error executing sample query: {e}")

    print("\nDatabase manager test completed")


if __name__ == "__main__":
    main()
