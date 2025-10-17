#!/usr/bin/env python3
"""
Quick script to check progress of ngram frequency population.
"""

import pymysql
from core.config import VocabularyConfig

def check_progress():
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        # Count total records
        cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE (phrase IS NULL OR phrase = 0) AND term NOT LIKE '% %'")
        total_single_words = cursor.fetchone()[0]

        # Count NULL records (not processed yet)
        cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE ngram_freq IS NULL AND (phrase IS NULL OR phrase = 0) AND term NOT LIKE '% %'")
        null_count = cursor.fetchone()[0]

        # Count processed records
        cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE ngram_freq IS NOT NULL AND (phrase IS NULL OR phrase = 0) AND term NOT LIKE '% %'")
        processed_count = cursor.fetchone()[0]

        # Count found vs not found
        cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE ngram_freq > -999 AND (phrase IS NULL OR phrase = 0) AND term NOT LIKE '% %'")
        found_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE ngram_freq = -999 AND (phrase IS NULL OR phrase = 0) AND term NOT LIKE '% %'")
        not_found_count = cursor.fetchone()[0]

        print(f"Ngram Frequency Population Progress:")
        print(f"  Total single words: {total_single_words:,}")
        print(f"  Processed: {processed_count:,} ({processed_count/total_single_words*100:.1f}%)")
        print(f"  Remaining: {null_count:,}")
        print(f"  Found frequencies: {found_count:,}")
        print(f"  Not found (-999): {not_found_count:,}")

        if processed_count > 0:
            print(f"  Success rate: {found_count/processed_count*100:.1f}%")

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    check_progress()