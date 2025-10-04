#!/usr/bin/env python3
"""Create the word_domains table in PostgreSQL."""

import psycopg
from core.secure_config import get_database_config

CREATE_WORD_DOMAINS_TABLE = """
CREATE TABLE IF NOT EXISTS word_domains (
    word_id INTEGER PRIMARY KEY REFERENCES defined(id) ON DELETE CASCADE,
    primary_domain VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_word_domains_primary_domain
ON word_domains(primary_domain)
"""

def main():
    """Create word_domains table."""
    config = get_database_config()

    conn = psycopg.connect(
        host=config.host,
        port=config.port,
        dbname=config.database,
        user=config.user,
        password=config.password,
        options=f'-c search_path={config.schema}'
    )

    cursor = conn.cursor()

    print("Creating word_domains table...")
    cursor.execute(CREATE_WORD_DOMAINS_TABLE)

    print("Creating index on primary_domain...")
    cursor.execute(CREATE_INDEX)

    conn.commit()

    # Verify
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = 'word_domains'
        ORDER BY ordinal_position
    """, (config.schema,))

    print("\nTable created successfully!")
    print("\nColumns:")
    for col_name, col_type in cursor.fetchall():
        print(f"  {col_name}: {col_type}")

    cursor.close()
    conn.close()

if __name__ == '__main__':
    main()
