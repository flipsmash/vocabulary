#!/usr/bin/env python3
"""Quick script to check similarity data status in the database."""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import psycopg
from core.config import VocabularyConfig

# Get connection params from config
conn_params = VocabularyConfig.get_db_config()

def check_similarity_data():
    """Check the current state of similarity data."""
    with psycopg.connect(**conn_params) as conn:
        with conn.cursor() as cur:
            print("=" * 80)
            print("SIMILARITY DATA STATUS")
            print("=" * 80)

            # Check total words
            cur.execute("SELECT COUNT(*) FROM vocab.defined")
            total_words = cur.fetchone()[0]
            print(f"Total words in database:        {total_words:>10,}")
            print()

            # Check embedding models and coverage
            cur.execute("""
                SELECT
                    embedding_model,
                    COUNT(*) as total_pairs,
                    MIN(created_at) as first_created,
                    MAX(created_at) as last_updated
                FROM vocab.definition_similarity
                GROUP BY embedding_model
                ORDER BY last_updated DESC
            """)

            models = cur.fetchall()
            if models:
                print("EMBEDDING MODELS:")
                print("-" * 80)
                for model, pairs, first, last in models:
                    print(f"\nModel: {model}")
                    print(f"  Total similarity pairs:       {pairs:>10,}")
                    print(f"  First created:                {first}")
                    print(f"  Last updated:                 {last}")

                    # Calculate coverage for this model
                    cur.execute("""
                        SELECT COUNT(DISTINCT word_id) FROM (
                            SELECT word1_id as word_id
                            FROM vocab.definition_similarity
                            WHERE embedding_model = %s
                            UNION
                            SELECT word2_id as word_id
                            FROM vocab.definition_similarity
                            WHERE embedding_model = %s
                        ) covered
                    """, (model, model))
                    words_with_similarities = cur.fetchone()[0]
                    coverage_pct = (words_with_similarities / total_words * 100) if total_words > 0 else 0
                    print(f"  Words with similarities:      {words_with_similarities:>10,} ({coverage_pct:.1f}% coverage)")

            else:
                print("No similarity data found!")

            print()
            print("=" * 80)

            # Check for words without ANY similarities
            cur.execute("""
                SELECT COUNT(*) FROM vocab.defined d
                WHERE NOT EXISTS (
                    SELECT 1 FROM vocab.definition_similarity ds
                    WHERE ds.word1_id = d.id OR ds.word2_id = d.id
                )
            """)
            words_without_similarities = cur.fetchone()[0]

            if words_without_similarities > 0:
                print(f"\n⚠️  WARNING: {words_without_similarities:,} words have NO similarities in any model")
                print("   Run scripts/maintain_similarity.py to generate missing similarities")
            else:
                print(f"\n✅ All words have similarity data")

            print()

            # Sample words without mpnet similarities
            cur.execute("""
                SELECT d.id, d.term
                FROM vocab.defined d
                WHERE NOT EXISTS (
                    SELECT 1 FROM vocab.definition_similarity ds
                    WHERE (ds.word1_id = d.id OR ds.word2_id = d.id)
                    AND ds.embedding_model = 'sentence-transformers/all-mpnet-base-v2'
                )
                LIMIT 10
            """)
            missing_mpnet = cur.fetchall()

            if missing_mpnet:
                print(f"Sample words missing mpnet similarities ({len(missing_mpnet)} shown):")
                for word_id, term in missing_mpnet:
                    print(f"  - {term} (ID: {word_id})")

            print()

if __name__ == '__main__':
    try:
        check_similarity_data()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
