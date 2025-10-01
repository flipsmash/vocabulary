#!/usr/bin/env python3
"""
Populate ngram frequencies using the working ngrams.py approach, but with:
- Very small batches (5-10 words at a time)
- Long delays between batches (30+ seconds)
- Resume capability
- Detailed progress tracking

This prioritizes coverage over speed - better to get real ngram data slowly
than accept 16,000 words as "not found".
"""

import os
import sys
import time
import subprocess
import pymysql
from typing import List, Tuple, Dict, Optional
from datetime import datetime

# Import the ngram functionality from temp/ngram.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'temp'))

def install_dependencies():
    """Install required dependencies if not available."""
    try:
        import google_ngram_downloader
        print("OK: google-ngram-downloader already installed")
    except ImportError:
        print("Installing google-ngram-downloader...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'google-ngram-downloader'])
        print("OK: google-ngram-downloader installed successfully")

def setup_imports():
    """Import required modules after ensuring dependencies are installed."""
    try:
        from temp.ngram import ngram_zipf
        return ngram_zipf
    except ImportError as e:
        print(f"Error importing ngram module: {e}")
        print("Make sure temp/ngram.py exists in the expected location")
        sys.exit(1)

class PatientNgramPopulator:
    def __init__(self):
        # Database setup
        from core.config import VocabularyConfig
        self.db_config = VocabularyConfig.get_db_config()

        # Ngram configuration - same as before but more patient
        self.corpus = "eng"
        self.year_start = 1900
        self.year_end = 2019
        self.aggregator = "mean"
        self.totalcounts_path = os.path.join(os.path.dirname(__file__), 'temp', 'total_counts')
        self.batch_size = 5  # Very small batches
        self.batch_delay = 45  # 45 seconds between batches
        self.not_found_value = -999

        # Progress tracking
        self.total_processed = 0
        self.total_found = 0
        self.total_errors = 0
        self.start_time = None

        # Import ngram function
        install_dependencies()
        self.ngram_zipf = setup_imports()

    def get_db_connection(self):
        """Create database connection."""
        return pymysql.connect(**self.db_config)

    def get_remaining_terms(self, limit: Optional[int] = None) -> List[Tuple[int, str]]:
        """Get terms that still need ngram_freq populated."""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Focus on words that don't have any frequency data yet
            query = """
                SELECT id, term
                FROM defined
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

    def process_small_batch(self, terms_batch: List[Tuple[int, str]]) -> Dict[str, int]:
        """Process a very small batch of terms."""
        if not terms_batch:
            return {'processed': 0, 'found': 0, 'errors': 0}

        words = [term for _, term in terms_batch]

        print(f"  Processing {len(words)} words: {', '.join(words)}")

        try:
            # Use working ngram approach but with patience
            scores = self.ngram_zipf(
                words,
                corpus=self.corpus,
                totalcounts_path=self.totalcounts_path,
                year_start=self.year_start,
                year_end=self.year_end,
                aggregator=self.aggregator,
                debug=False  # Reduce noise
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
                        print(f"    FOUND {term}: {score:.3f}")
                    else:
                        score = self.not_found_value
                        print(f"    NOT FOUND {term}: set to {self.not_found_value}")

                    cursor.execute(
                        "UPDATE defined SET ngram_freq = %s WHERE id = %s",
                        (score, term_id)
                    )

                conn.commit()
                print(f"    Updated {len(terms_batch)} records, found {found_count} scores")

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
        """Main execution with patience and detailed progress."""
        print("=" * 60)
        print("Patient Ngram Frequency Populator")
        print("=" * 60)
        print(f"Configuration:")
        print(f"  Corpus: {self.corpus}")
        print(f"  Years: {self.year_start}-{self.year_end}")
        print(f"  Batch size: {self.batch_size}")
        print(f"  Delay between batches: {self.batch_delay}s")
        print(f"  Total counts file: {self.totalcounts_path}")

        # Check total counts file
        if not os.path.exists(self.totalcounts_path):
            print(f"ERROR: Total counts file not found: {self.totalcounts_path}")
            return False

        # Get remaining work
        remaining_terms = self.get_remaining_terms()
        print(f"\nTerms remaining to process: {len(remaining_terms)}")

        if not remaining_terms:
            print("No terms need processing!")
            return True

        # Estimate time
        batches_needed = (len(remaining_terms) + self.batch_size - 1) // self.batch_size
        estimated_minutes = (batches_needed * self.batch_delay) / 60
        print(f"Estimated batches: {batches_needed}")
        print(f"Estimated time: {estimated_minutes:.1f} minutes")

        print("\nStarting patient processing automatically...")

        # Start processing
        self.start_time = time.time()
        batch_num = 0

        while True:
            # Get next small batch
            current_batch = self.get_remaining_terms(self.batch_size)

            if not current_batch:
                print("\nAll terms processed!")
                break

            batch_num += 1
            print(f"\nBatch #{batch_num} of ~{batches_needed}")

            # Process this batch
            batch_stats = self.process_small_batch(current_batch)

            # Update totals
            self.total_processed += batch_stats['processed']
            self.total_found += batch_stats['found']
            self.total_errors += batch_stats['errors']

            # Show progress
            elapsed = time.time() - self.start_time
            remaining_count = len(self.get_remaining_terms())

            print(f"  Progress: {self.total_processed} processed, {self.total_found} found, {remaining_count} remaining")
            print(f"  Time elapsed: {elapsed/60:.1f}m")

            # Respectful delay before next batch
            if remaining_count > 0:
                print(f"  Waiting {self.batch_delay}s before next batch...")
                time.sleep(self.batch_delay)

        # Final summary
        elapsed = time.time() - self.start_time
        print(f"\nProcessing Complete!")
        print(f"  Total processed: {self.total_processed}")
        print(f"  Total found: {self.total_found}")
        print(f"  Total errors: {self.total_errors}")
        print(f"  Success rate: {self.total_found/self.total_processed*100:.1f}%")
        print(f"  Total time: {elapsed/60:.1f} minutes")

        return True

if __name__ == "__main__":
    try:
        populator = PatientNgramPopulator()
        success = populator.run()

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