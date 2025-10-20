#!/usr/bin/env python3
"""Quick script to check frequency data status in the database."""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import psycopg
from core.config import VocabularyConfig

# Get connection params from config
conn_params = VocabularyConfig.get_db_config()

def check_frequency_data():
    """Check the current state of frequency data."""
    with psycopg.connect(**conn_params) as conn:
        with conn.cursor() as cur:
            # Check frequency data coverage
            cur.execute("""
                SELECT
                    COUNT(*) as total_words,
                    COUNT(python_wordfreq) as has_python_wordfreq,
                    COUNT(CASE WHEN python_wordfreq IS NOT NULL AND python_wordfreq != -999 THEN 1 END) as valid_python_wordfreq,
                    COUNT(ngram_freq) as has_ngram_freq,
                    COUNT(CASE WHEN ngram_freq IS NOT NULL AND ngram_freq != -999 THEN 1 END) as valid_ngram_freq,
                    COUNT(commoncrawl_freq) as has_commoncrawl_freq,
                    COUNT(CASE WHEN commoncrawl_freq IS NOT NULL AND commoncrawl_freq != -999 THEN 1 END) as valid_commoncrawl_freq,
                    COUNT(final_rarity) as has_final_rarity
                FROM vocab.defined;
            """)

            result = cur.fetchone()
            print("=" * 70)
            print("FREQUENCY DATA STATUS")
            print("=" * 70)
            print(f"Total words:                    {result[0]:>10,}")
            print()
            print(f"python_wordfreq (has/valid):    {result[1]:>10,} / {result[2]:>10,}")
            print(f"ngram_freq (has/valid):         {result[3]:>10,} / {result[4]:>10,}")
            print(f"commoncrawl_freq (has/valid):   {result[5]:>10,} / {result[6]:>10,}")
            print()
            print(f"final_rarity (populated):       {result[7]:>10,}")
            print("=" * 70)

            # Check materialized view exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_matviews
                    WHERE schemaname = 'vocab' AND matviewname = 'word_rarity_metrics'
                );
            """)

            view_exists = cur.fetchone()[0]
            print(f"\nMaterialized view 'word_rarity_metrics': {'EXISTS' if view_exists else 'MISSING'}")

            if view_exists:
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(final_rarity) as with_rarity,
                        MAX(calculated_at) as last_refresh
                    FROM word_rarity_metrics;
                """)
                view_result = cur.fetchone()
                print(f"  - Total rows:       {view_result[0]:>10,}")
                print(f"  - With rarity:      {view_result[1]:>10,}")
                print(f"  - Last refresh:     {view_result[2]}")

if __name__ == '__main__':
    try:
        check_frequency_data()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
