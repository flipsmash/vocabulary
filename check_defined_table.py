#!/usr/bin/env python3
"""
Check the structure of the defined table to understand the ngram_freq field
"""

import pymysql
from core.config import VocabularyConfig

def check_defined_table():
    config = VocabularyConfig.get_db_config()

    conn = pymysql.connect(**config)
    cursor = conn.cursor()

    try:
        # Check table structure
        print("=== DEFINED TABLE STRUCTURE ===")
        cursor.execute("DESCRIBE defined")
        columns = cursor.fetchall()
        for col in columns:
            print(f"{col[0]:<20} {col[1]:<15} {col[2]:<8} {col[3]:<8} {str(col[4]):<10} {str(col[5])}")

        print("\n=== SAMPLE DATA ===")
        cursor.execute("SELECT id, term, ngram_freq FROM vocab.defined WHERE ngram_freq IS NOT NULL LIMIT 5")
        sample_with_freq = cursor.fetchall()
        print("Sample records WITH ngram_freq:")
        for row in sample_with_freq:
            print(f"ID: {row[0]}, Term: {row[1]}, ngram_freq: {row[2]}")

        cursor.execute("SELECT id, term, ngram_freq FROM vocab.defined WHERE ngram_freq IS NULL LIMIT 5")
        sample_without_freq = cursor.fetchall()
        print("\nSample records WITHOUT ngram_freq:")
        for row in sample_without_freq:
            print(f"ID: {row[0]}, Term: {row[1]}, ngram_freq: {row[2]}")

        print("\n=== COUNTS ===")
        cursor.execute("SELECT COUNT(*) FROM vocab.defined")
        total_count = cursor.fetchone()[0]
        print(f"Total records: {total_count}")

        cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE ngram_freq IS NOT NULL")
        with_freq_count = cursor.fetchone()[0]
        print(f"Records with ngram_freq: {with_freq_count}")

        cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE ngram_freq IS NULL")
        without_freq_count = cursor.fetchone()[0]
        print(f"Records without ngram_freq: {without_freq_count}")

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    check_defined_table()