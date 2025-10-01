#!/usr/bin/env python3
"""
Check the status of python_wordfreq field in the defined table.
"""

import pymysql
from core.config import VocabularyConfig

def check_wordfreq_status():
    """Check how many records need python_wordfreq populated."""
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        # Check total records
        cursor.execute("SELECT COUNT(*) FROM defined")
        total_count = cursor.fetchone()[0]

        # Check NULL python_wordfreq
        cursor.execute("SELECT COUNT(*) FROM defined WHERE python_wordfreq IS NULL")
        null_count = cursor.fetchone()[0]

        # Check populated python_wordfreq
        cursor.execute("SELECT COUNT(*) FROM defined WHERE python_wordfreq IS NOT NULL")
        populated_count = cursor.fetchone()[0]

        # Check if column exists
        cursor.execute("SHOW COLUMNS FROM defined LIKE 'python_wordfreq'")
        column_exists = cursor.fetchone() is not None

        print(f"Python WordFreq Status:")
        print(f"  Column exists: {column_exists}")
        print(f"  Total records: {total_count:,}")
        print(f"  NULL python_wordfreq: {null_count:,}")
        print(f"  Populated python_wordfreq: {populated_count:,}")

        if null_count > 0:
            print(f"  Need to process: {null_count:,} records")
        else:
            print(f"  All records already have python_wordfreq values")

        return null_count > 0

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    needs_processing = check_wordfreq_status()
    if needs_processing:
        print("\nSome records need python_wordfreq populated.")
    else:
        print("\nAll records already have python_wordfreq values.")