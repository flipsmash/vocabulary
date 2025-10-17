#!/usr/bin/env python3
"""
Repopulate all ngram frequencies using the fixed local Google Books data.
Processes all terms in batches and sets -999 for words not found.
"""

import os
import sys
import time
import pymysql
from typing import List, Tuple, Dict
from datetime import datetime

# Import our fixed ngram lookup function
from ngram_lookup import lookup_terms

class NgramRepopulator:
    def __init__(self):
        from core.config import VocabularyConfig
        self.db_config = VocabularyConfig.get_db_config()

        # Processing settings
        self.batch_size = 100  # Process 100 words at a time
        self.not_found_value = -999

        # Progress tracking
        self.total_processed = 0
        self.total_found = 0
        self.start_time = None

    def get_db_connection(self):
        """Create database connection."""
        return pymysql.connect(**self.db_config)

    def get_remaining_terms(self, limit=None) -> List[Tuple[int, str]]:
        """Get terms that still need ngram_freq populated."""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            query = """
                SELECT id, term
                FROM vocab.defined
                WHERE ngram_freq IS NULL
                AND (phrase IS NULL OR phrase = 0)
                AND term NOT LIKE '% %'
                ORDER BY id
            """

            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query)
            results = cursor.fetchall()
            return [(row[0], row[1].strip()) for row in results if row[1] and row[1].strip()]

        finally:
            cursor.close()
            conn.close()

    def process_batch(self, terms_batch: List[Tuple[int, str]]) -> Dict[str, int]:
        """Process a batch of terms using the fixed ngram lookup."""
        if not terms_batch:
            return {'processed': 0, 'found': 0, 'errors': 0}

        words = [term for _, term in terms_batch]
        print(f"  Processing batch of {len(words)} words...")

        try:
            # Use the fixed ngram lookup
            scores = lookup_terms(
                words,
                year_start=1900,
                year_end=2019,
                aggregator="mean",
                alpha=1e-6,
                verbose=False  # Keep it quiet for batch processing
            )

            # Update database immediately for this batch
            conn = self.get_db_connection()
            cursor = conn.cursor()

            try:
                found_count = 0
                for term_id, term in terms_batch:
                    score = scores.get(term.lower())
                    if score is not None:
                        found_count += 1
                    else:
                        score = self.not_found_value

                    cursor.execute(
                        "UPDATE vocab.defined SET ngram_freq = %s WHERE id = %s",
                        (score, term_id)
                    )

                conn.commit()
                print(f"    Updated {len(terms_batch)} records, found {found_count} frequencies")

                return {
                    'processed': len(terms_batch),
                    'found': found_count,
                    'errors': 0
                }

            finally:
                cursor.close()
                conn.close()

        except Exception as e:
            print(f"    ERROR processing batch: {e}")
            return {
                'processed': len(terms_batch),
                'found': 0,
                'errors': len(terms_batch)
            }

    def run(self):
        """Main execution."""
        print("=" * 60)
        print("Ngram Frequency Repopulator (Fixed Local Data)")
        print("=" * 60)

        # Check if we have the required data
        if not os.path.exists("temp/ngram_data"):
            print("ERROR: Ngram data directory not found: temp/ngram_data")
            print("Run download_ngram_data.py first to download the data")
            return False

        if not os.path.exists("temp/total_counts"):
            print("ERROR: Total counts file not found: temp/total_counts")
            return False

        # Get remaining work
        remaining_terms = self.get_remaining_terms()
        print(f"Terms remaining to process: {len(remaining_terms):,}")

        if not remaining_terms:
            print("No terms need processing!")
            return True

        # Estimate time (this will be much faster than API approach)
        batches_needed = (len(remaining_terms) + self.batch_size - 1) // self.batch_size
        print(f"Processing in {batches_needed:,} batches of {self.batch_size} words each")

        print("\nStarting repopulation...")

        # Start processing
        self.start_time = time.time()
        batch_num = 0

        while True:
            # Get next batch
            current_batch = self.get_remaining_terms(self.batch_size)

            if not current_batch:
                print("\nAll terms processed!")
                break

            batch_num += 1
            elapsed = time.time() - self.start_time

            print(f"\nBatch #{batch_num:,} of ~{batches_needed:,} (elapsed: {elapsed/60:.1f}m)")

            # Process this batch
            batch_stats = self.process_batch(current_batch)

            # Update totals
            self.total_processed += batch_stats['processed']
            self.total_found += batch_stats['found']

            # Show progress
            remaining_count = len(self.get_remaining_terms())
            completion_pct = (self.total_processed / (self.total_processed + remaining_count)) * 100

            print(f"    Progress: {self.total_processed:,} processed, {self.total_found:,} found")
            print(f"    Remaining: {remaining_count:,} ({completion_pct:.1f}% complete)")

            # Estimate time remaining
            if batch_num > 1:  # Need at least 2 batches for estimate
                avg_time_per_batch = elapsed / batch_num
                remaining_batches = remaining_count / self.batch_size
                estimated_remaining = (remaining_batches * avg_time_per_batch) / 60
                print(f"    Estimated time remaining: {estimated_remaining:.1f} minutes")

        # Final summary
        elapsed = time.time() - self.start_time
        print(f"\nRepopulation Complete!")
        print(f"  Total processed: {self.total_processed:,}")
        print(f"  Total found: {self.total_found:,}")
        print(f"  Not found (set to -999): {self.total_processed - self.total_found:,}")
        print(f"  Success rate: {self.total_found/self.total_processed*100:.1f}%")
        print(f"  Total time: {elapsed/60:.1f} minutes")

        return True

if __name__ == "__main__":
    try:
        repopulator = NgramRepopulator()
        success = repopulator.run()

        if success:
            print("\nOperation completed successfully!")
        else:
            print("\nOperation failed!")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)