#!/usr/bin/env python3
"""
Classify all vocabulary terms using domain_classifier.py and store in word_domains table.

This script reads all terms from the defined table, runs the domain classifier,
and stores the results in the word_domains table.
"""

import sys
import logging
from pathlib import Path
from typing import List, Tuple
import psycopg
from core.secure_config import get_database_config

# Import the domain classifier
from domain_classifier import DomainClassifier

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fetch_all_terms() -> List[Tuple[int, str, str]]:
    """Fetch all terms with definitions from defined table."""
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

    logger.info("Fetching all terms from defined table...")
    cursor.execute("""
        SELECT id, term, definition
        FROM defined
        WHERE definition IS NOT NULL
        ORDER BY id
    """)

    results = cursor.fetchall()
    cursor.close()
    conn.close()

    logger.info(f"Fetched {len(results):,} terms with definitions")
    return results


def classify_and_store(batch_size: int = 500):
    """Classify all terms and store results in word_domains table."""

    # Initialize the domain classifier
    logger.info("Initializing domain classifier...")
    classifier = DomainClassifier()

    # Fetch all terms
    all_terms = fetch_all_terms()

    if not all_terms:
        logger.warning("No terms found to classify")
        return

    # Get database connection
    config = get_database_config()
    conn = psycopg.connect(
        host=config.host,
        port=config.port,
        dbname=config.database,
        user=config.user,
        password=config.password,
        options=f'-c search_path={config.schema}'
    )

    # Process in batches
    total_processed = 0
    total_batches = (len(all_terms) + batch_size - 1) // batch_size

    logger.info(f"Processing {len(all_terms):,} terms in {total_batches} batches of {batch_size}")

    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(all_terms))
        batch = all_terms[start_idx:end_idx]

        # Extract IDs, terms, and definitions for this batch
        word_ids = [item[0] for item in batch]
        terms = [item[1] for item in batch]
        definitions = [item[2] for item in batch]

        # Classify the batch
        logger.info(f"Classifying batch {batch_num + 1}/{total_batches} ({len(batch)} terms)...")
        results = classifier.classify_batch(terms, definitions)

        # Prepare data for database insertion
        records_to_insert = []
        for word_id, result in zip(word_ids, results):
            records_to_insert.append((
                word_id,
                result['primary_domain'],
                result['confidence']
            ))

        # Insert/update in database
        cursor = conn.cursor()
        try:
            # Use UPSERT to handle any existing records
            cursor.executemany("""
                INSERT INTO word_domains (word_id, primary_domain)
                VALUES (%s, %s)
                ON CONFLICT (word_id)
                DO UPDATE SET primary_domain = EXCLUDED.primary_domain
            """, [(wid, domain) for wid, domain, _ in records_to_insert])

            conn.commit()
        finally:
            cursor.close()

        total_processed += len(batch)
        logger.info(f"Progress: {total_processed:,}/{len(all_terms):,} ({100.0*total_processed/len(all_terms):.1f}%)")

    # Verify results
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM word_domains")
        count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT primary_domain, COUNT(*) as count
            FROM word_domains
            GROUP BY primary_domain
            ORDER BY count DESC
        """)

        print("\n" + "=" * 80)
        print("DOMAIN CLASSIFICATION COMPLETE")
        print("=" * 80)
        print(f"\nTotal terms classified: {count:,}")
        print("\nDomain distribution:")
        print("-" * 80)

        for domain, domain_count in cursor.fetchall():
            pct = 100.0 * domain_count / count
            print(f"  {domain:45s} {domain_count:6,} ({pct:5.1f}%)")

    conn.close()
    logger.info("Classification complete!")


def main():
    """Main entry point."""
    try:
        classify_and_store(batch_size=500)
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
