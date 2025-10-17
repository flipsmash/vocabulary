#!/usr/bin/env python3
"""
Populate ngram_freq field for all terms in the defined table using Google Books ngrams.

Features:
- Processes in batches of 100 (good netizen)
- Resumes gracefully from where it left off
- Skips multi-word terms (phrases)
- Uses 1900-2019 date range for better coverage of old/obsolete words
- Sets unfound words to -999
- Auto-installs dependencies
- Comprehensive progress tracking and logging
"""

import os
import sys
import time
import subprocess
import pymysql
from typing import List, Dict, Optional, Tuple
from datetime import datetime

# Import the ngram functionality from temp/ngram.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'temp'))

def install_dependencies():
    """Install required dependencies if not available."""
    try:
        import google_ngram_downloader
        print("✓ google-ngram-downloader already installed")
    except ImportError:
        print("Installing google-ngram-downloader...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'google-ngram-downloader'])
        print("✓ google-ngram-downloader installed successfully")

def setup_imports():
    """Import required modules after ensuring dependencies are installed."""
    try:
        from temp.ngram import ngram_zipf
        return ngram_zipf
    except ImportError as e:
        print(f"Error importing ngram module: {e}")
        print("Make sure temp/ngram.py exists in the expected location")
        sys.exit(1)

class NgramFrequencyPopulator:
    def __init__(self):
        # Database setup
        from core.config import VocabularyConfig
        self.db_config = VocabularyConfig.get_db_config()

        # Ngram configuration
        self.corpus = "eng"
        self.year_start = 1900
        self.year_end = 2019
        self.aggregator = "mean"
        self.totalcounts_path = os.path.join(os.path.dirname(__file__), 'temp', 'total_counts')
        self.batch_size = 100
        self.not_found_value = -999

        # Progress tracking
        self.total_processed = 0
        self.total_updated = 0
        self.total_skipped = 0
        self.total_errors = 0
        self.start_time = None

        # Import ngram function
        install_dependencies()
        self.ngram_zipf = setup_imports()

    def get_db_connection(self):
        """Create database connection."""
        return pymysql.connect(**self.db_config)

    def get_unprocessed_terms(self, limit: Optional[int] = None) -> List[Tuple[int, str]]:
        """Get terms that need ngram_freq populated, excluding multi-word terms."""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            query = """
                SELECT id, term
                FROM vocab.defined
                WHERE ngram_freq IS NULL
                AND (phrase IS NULL OR phrase = 0)
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

    def get_progress_stats(self) -> Dict[str, int]:
        """Get current progress statistics."""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Total records
            cursor.execute("SELECT COUNT(*) FROM vocab.defined")
            total_records = cursor.fetchone()[0]

            # Records with ngram_freq
            cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE ngram_freq IS NOT NULL")
            completed_records = cursor.fetchone()[0]

            # Multi-word terms (phrases) that we skip
            cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE phrase = 1")
            phrase_records = cursor.fetchone()[0]

            # Remaining single-word terms to process
            cursor.execute("""
                SELECT COUNT(*) FROM vocab.defined
                WHERE ngram_freq IS NULL
                AND (phrase IS NULL OR phrase = 0)
            """)
            remaining_records = cursor.fetchone()[0]

            return {
                'total_records': total_records,
                'completed_records': completed_records,
                'phrase_records': phrase_records,
                'remaining_records': remaining_records
            }

        finally:
            cursor.close()
            conn.close()

    def update_ngram_frequencies(self, term_scores: Dict[int, float]) -> int:
        """Update ngram_freq values in database."""
        if not term_scores:
            return 0

        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            updated_count = 0
            for term_id, score in term_scores.items():
                cursor.execute(
                    "UPDATE vocab.defined SET ngram_freq = %s WHERE id = %s",
                    (score, term_id)
                )
                updated_count += cursor.rowcount

            conn.commit()
            return updated_count

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def process_batch(self, terms_batch: List[Tuple[int, str]]) -> Dict[str, int]:
        """Process a batch of terms and return statistics."""
        if not terms_batch:
            return {'processed': 0, 'updated': 0, 'errors': 0}

        # Extract just the words for ngram lookup
        words = [term for _, term in terms_batch]

        print(f"  Processing batch of {len(words)} words...")
        print(f"  Sample words: {', '.join(words[:5])}{'...' if len(words) > 5 else ''}")

        try:
            # Get ngram scores
            scores = self.ngram_zipf(
                words,
                corpus=self.corpus,
                totalcounts_path=self.totalcounts_path,
                year_start=self.year_start,
                year_end=self.year_end,
                aggregator=self.aggregator,
                debug=False
            )

            # Prepare updates with term IDs
            term_scores = {}
            found_count = 0

            for term_id, term in terms_batch:
                score = scores.get(term.lower())
                if score is not None:
                    term_scores[term_id] = score
                    found_count += 1
                else:
                    term_scores[term_id] = self.not_found_value

            # Update database
            updated_count = self.update_ngram_frequencies(term_scores)

            print(f"    ✓ Found scores for {found_count}/{len(words)} words")
            print(f"    ✓ Updated {updated_count} database records")

            return {
                'processed': len(terms_batch),
                'updated': updated_count,
                'errors': 0
            }

        except Exception as e:
            print(f"    ✗ Error processing batch: {e}")
            return {
                'processed': len(terms_batch),
                'updated': 0,
                'errors': len(terms_batch)
            }

    def print_progress(self, batch_num: int, batch_stats: Dict[str, int],
                      overall_stats: Dict[str, int]):
        """Print detailed progress information."""
        if self.start_time:
            elapsed = time.time() - self.start_time
            rate = self.total_processed / elapsed if elapsed > 0 else 0

            # Estimate remaining time
            remaining = overall_stats['remaining_records'] - batch_stats['processed']
            eta_seconds = remaining / rate if rate > 0 else 0
            eta_str = f"{eta_seconds/60:.1f}m" if eta_seconds > 60 else f"{eta_seconds:.0f}s"

            print(f"\n📊 Progress Report (Batch #{batch_num}):")
            print(f"   Batch: {batch_stats['processed']} processed, {batch_stats['updated']} updated, {batch_stats['errors']} errors")
            print(f"   Total: {self.total_processed:,} processed, {self.total_updated:,} updated, {self.total_errors:,} errors")
            print(f"   Remaining: {remaining:,} records")
            print(f"   Rate: {rate:.1f} records/sec")
            print(f"   ETA: {eta_str}")
            print(f"   Progress: {overall_stats['completed_records']:,}/{overall_stats['total_records']:,} " +
                  f"({overall_stats['completed_records']/overall_stats['total_records']*100:.1f}%)")

    def run(self):
        """Main execution method."""
        print("🚀 Starting ngram frequency population...")
        print(f"Configuration:")
        print(f"  Corpus: {self.corpus}")
        print(f"  Years: {self.year_start}-{self.year_end}")
        print(f"  Aggregator: {self.aggregator}")
        print(f"  Batch size: {self.batch_size}")
        print(f"  Not found value: {self.not_found_value}")
        print(f"  Total counts file: {self.totalcounts_path}")

        # Check if total counts file exists
        if not os.path.exists(self.totalcounts_path):
            print(f"❌ Total counts file not found: {self.totalcounts_path}")
            print("Please ensure the total_counts file exists in the temp/ directory")
            return False

        # Get initial statistics
        stats = self.get_progress_stats()
        print(f"\n📈 Database Statistics:")
        print(f"  Total records: {stats['total_records']:,}")
        print(f"  Already completed: {stats['completed_records']:,}")
        print(f"  Multi-word terms (skipped): {stats['phrase_records']:,}")
        print(f"  Remaining to process: {stats['remaining_records']:,}")

        if stats['remaining_records'] == 0:
            print("✅ All terms already have ngram frequencies!")
            return True

        # Start processing
        self.start_time = time.time()
        batch_num = 0

        while True:
            # Get next batch
            terms_batch = self.get_unprocessed_terms(self.batch_size)

            if not terms_batch:
                print("\n✅ All terms processed!")
                break

            batch_num += 1
            print(f"\n🔄 Processing batch #{batch_num} ({len(terms_batch)} terms)...")

            # Process batch
            batch_stats = self.process_batch(terms_batch)

            # Update totals
            self.total_processed += batch_stats['processed']
            self.total_updated += batch_stats['updated']
            self.total_errors += batch_stats['errors']

            # Print progress
            current_stats = self.get_progress_stats()
            self.print_progress(batch_num, batch_stats, current_stats)

            # Be a good netizen - small delay between batches
            time.sleep(1)

        # Final summary
        elapsed = time.time() - self.start_time
        print(f"\n🎉 Processing Complete!")
        print(f"  Total time: {elapsed/60:.1f} minutes")
        print(f"  Records processed: {self.total_processed:,}")
        print(f"  Records updated: {self.total_updated:,}")
        print(f"  Errors: {self.total_errors:,}")
        print(f"  Average rate: {self.total_processed/elapsed:.1f} records/sec")

        return True

def main():
    """Main entry point."""
    print("=" * 60)
    print("🔤 Vocabulary Ngram Frequency Populator")
    print("=" * 60)

    try:
        populator = NgramFrequencyPopulator()
        success = populator.run()

        if success:
            print("\n✅ Operation completed successfully!")
        else:
            print("\n❌ Operation failed!")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n⏹️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()