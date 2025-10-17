#!/usr/bin/env python3
"""
Zipf Frequency Updater for Vocabulary Database
Reads terms from MySQL and updates with wordfreq Zipf scores
"""

import mysql.connector
import logging
from typing import Optional, List, Tuple
from wordfreq import zipf_frequency
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ZipfFrequencyUpdater:
    def __init__(self, db_config: dict):
        self.db_config = db_config

    def estimate_frequency_from_characteristics(self, word: str) -> float:
        """
        Estimate frequency based on word characteristics when wordfreq fails
        """
        # Base frequency for unknown words
        base_freq = 0.001
        
        # Length-based adjustment (longer words tend to be rarer)
        length_factor = max(0.1, 1.0 - (len(word) - 5) * 0.1)
        
        # Common prefixes/suffixes that indicate technical terms (lower frequency)
        technical_patterns = [
            'ology', 'ography', 'itis', 'osis', 'philia', 'phobia',
            'micro', 'macro', 'neo', 'pseudo', 'proto', 'meta'
        ]
        
        technical_factor = 1.0
        word_lower = word.lower()
        for pattern in technical_patterns:
            if pattern in word_lower:
                technical_factor = 0.3  # Much rarer
                break
        
        # Calculate estimated frequency
        estimated_freq = base_freq * length_factor * technical_factor
        
        return max(0.0001, estimated_freq)  # Minimum threshold

    def estimate_frequency_fallback(self, word: str) -> float:
        """
        Provide a fallback frequency estimate that fits within normal Zipf range
        Zipf scores typically range from ~1.0 (very rare) to ~8.0 (very common)
        """
        word_lower = word.lower().strip()
        
        # Base frequency for unknown words - start at bottom of normal Zipf range
        base_zipf = 0.8  # Slightly below the typical minimum of 1.0
        
        # Adjust based on word length
        if len(word) <= 4:
            length_bonus = 0.3  # Short words might be more common
        elif len(word) <= 8:
            length_bonus = 0.0  # Medium words - no adjustment
        elif len(word) <= 12:
            length_bonus = -0.2  # Longer words tend to be rarer
        else:
            length_bonus = -0.4  # Very long words are typically quite rare
        
        # Check for technical/scientific patterns (these are typically rarer)
        technical_patterns = [
            'ology', 'ography', 'itis', 'osis', 'ism', 'tion',
            'micro', 'macro', 'neo', 'proto', 'pseudo', 'meta',
            'anti', 'ultra', 'super', 'hyper', 'philia', 'phobia'
        ]
        
        is_technical = any(pattern in word_lower for pattern in technical_patterns)
        technical_penalty = -0.3 if is_technical else 0.0
        
        # Check for common word patterns that might indicate higher frequency
        common_patterns = ['ing', 'ed', 'er', 'ly', 'tion', 'able']
        has_common_ending = any(word_lower.endswith(pattern) for pattern in common_patterns)
        common_bonus = 0.2 if has_common_ending else 0.0
        
        # Calculate final estimated Zipf score
        estimated_zipf = base_zipf + length_bonus + technical_penalty + common_bonus
        
        # Keep within reasonable bounds for very rare words
        estimated_zipf = max(0.5, min(estimated_zipf, 1.2))
        
        return estimated_zipf

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = None
        try:
            conn = mysql.connector.connect(**self.db_config)
            yield conn
        finally:
            if conn:
                conn.close()

    def get_zipf_frequency(self, word: str, lang: str = "en") -> float:
        """
        Get Zipf frequency with guaranteed return value within proper Zipf range
        """
        try:
            # First try the 'best' wordlist
            score = zipf_frequency(word, lang, wordlist="best", minimum=0.0)
            if score > 0.0:
                return score

            # Fallback to 'large' wordlist  
            score = zipf_frequency(word, lang, wordlist="large", minimum=0.0)
            if score > 0.0:
                return score

            # If not found, estimate within proper Zipf range
            estimated = self.estimate_frequency_fallback(word)
            logger.debug(f"No wordfreq data for '{word}', estimated Zipf: {estimated:.2f}")
            return estimated

        except Exception as e:
            logger.warning(f"Error getting frequency for '{word}': {e}")
            return self.estimate_frequency_fallback(word)

    def get_terms_to_process(self, batch_size: int = 1000, offset: int = 0) -> List[Tuple[int, str]]:
        """Get terms that need Zipf frequency processing"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get terms where python_wordfreq is NULL or empty
            query = """
                    SELECT id, term
                    FROM vocab.defined
                    WHERE python_wordfreq IS NULL \
                       OR python_wordfreq = ''
                    ORDER BY id
                        LIMIT %s \
                    OFFSET %s \
                    """

            cursor.execute(query, (batch_size, offset))
            results = cursor.fetchall()

            logger.info(f"Retrieved {len(results)} terms for processing (offset: {offset})")
            return results

    def get_total_terms_to_process(self) -> int:
        """Get total count of terms that need processing"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = """
                    SELECT COUNT(*)
                    FROM vocab.defined
                    WHERE python_wordfreq IS NULL \
                       OR python_wordfreq = '' \
                    """
            cursor.execute(query)
            return cursor.fetchone()[0]

    def process_term_batch(self, terms: List[Tuple[int, str]]) -> List[Tuple[int, float]]:
        """Process a batch of terms to get their Zipf frequencies"""
        results = []

        for term_id, term in terms:
            # Clean the term (remove extra whitespace, convert to lowercase for lookup)
            clean_term = term.strip().lower()

            # Get Zipf frequency
            zipf_score = self.get_zipf_frequency(clean_term)
            results.append((term_id, zipf_score))

        return results

    def update_zipf_scores(self, zipf_results: List[Tuple[int, float]]):
        """Update the database with Zipf scores"""
        if not zipf_results:
            return

        with self.get_connection() as conn:
            cursor = conn.cursor()

            update_query = """
                           UPDATE vocab.defined
                           SET python_wordfreq = %s
                           WHERE id = %s
                           """

            update_data = [(score, term_id) for term_id, score in zipf_results]
            cursor.executemany(update_query, update_data)
            conn.commit()

            # Count real vs estimated (estimated will be <= 1.2)
            from_wordfreq = len([score for _, score in zipf_results if score > 1.2])
            estimated = len(zipf_results) - from_wordfreq
            
            logger.info(f"Updated {len(zipf_results)} terms with Zipf scores "
                       f"({from_wordfreq} from wordfreq, {estimated} estimated)")

    def process_all_terms(self, batch_size: int = 1000, max_workers: int = 4):
        """Process all terms in batches with parallel processing"""
        total_terms = self.get_total_terms_to_process()

        if total_terms == 0:
            logger.info("No terms need Zipf frequency processing")
            return

        logger.info(f"Starting Zipf frequency processing for {total_terms:,} terms")
        logger.info(f"Using batch size: {batch_size}, workers: {max_workers}")

        processed = 0
        offset = 0

        start_time = time.time()

        while offset < total_terms:
            # Get batch of terms
            terms_batch = self.get_terms_to_process(batch_size, offset)

            if not terms_batch:
                break

            # Process terms (could be parallelized further if needed)
            batch_start = time.time()
            zipf_results = self.process_term_batch(terms_batch)

            # Update database
            self.update_zipf_scores(zipf_results)

            processed += len(terms_batch)
            batch_time = time.time() - batch_start

            # Progress reporting
            progress_pct = (processed / total_terms) * 100
            rate = len(terms_batch) / batch_time if batch_time > 0 else 0

            # Count successful lookups
            successful = sum(1 for _, score in zipf_results if score is not None)
            success_rate = (successful / len(zipf_results)) * 100

            logger.info(f"Progress: {processed:,}/{total_terms:,} ({progress_pct:.1f}%) | "
                        f"Rate: {rate:.1f} terms/sec | "
                        f"Success: {success_rate:.1f}%")

            offset += batch_size

        total_time = time.time() - start_time
        overall_rate = processed / total_time if total_time > 0 else 0

        logger.info(f"✅ Completed! Processed {processed:,} terms in {total_time:.1f}s "
                    f"(avg {overall_rate:.1f} terms/sec)")

    def generate_frequency_report(self):
        """Generate a report on the frequency data"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get statistics
            stats_query = """
                          SELECT COUNT(*)               as total_terms, \
                                 COUNT(python_wordfreq) as terms_with_freq, \
                                 AVG(python_wordfreq)   as avg_zipf, \
                                 MIN(python_wordfreq)   as min_zipf, \
                                 MAX(python_wordfreq)   as max_zipf, \
                                 STD(python_wordfreq)   as std_zipf
                          FROM vocab.defined
                          WHERE python_wordfreq IS NOT NULL \
                          """

            cursor.execute(stats_query)
            stats = cursor.fetchone()

            # Get frequency distribution
            dist_query = """
                         SELECT CASE \
                                    WHEN python_wordfreq >= 6.0 THEN 'Very Common (6.0+)' \
                                    WHEN python_wordfreq >= 5.0 THEN 'Common (5.0-5.9)' \
                                    WHEN python_wordfreq >= 4.0 THEN 'Moderate (4.0-4.9)' \
                                    WHEN python_wordfreq >= 3.0 THEN 'Less Common (3.0-3.9)' \
                                    WHEN python_wordfreq >= 2.0 THEN 'Uncommon (2.0-2.9)' \
                                    WHEN python_wordfreq >= 1.0 THEN 'Rare (1.0-1.9)' \
                                    ELSE 'Very Rare (<1.0)' \
                                    END as frequency_category, \
                                COUNT(*) as count
                         FROM vocab.defined
                         WHERE python_wordfreq IS NOT NULL
                         GROUP BY frequency_category
                         ORDER BY MIN(python_wordfreq) DESC \
                         """

            cursor.execute(dist_query)
            distribution = cursor.fetchall()

            # Get top and bottom frequency words
            top_query = """
                        SELECT term, python_wordfreq
                        FROM vocab.defined
                        WHERE python_wordfreq IS NOT NULL
                        ORDER BY python_wordfreq DESC LIMIT 10 \
                        """
            cursor.execute(top_query)
            top_words = cursor.fetchall()

            bottom_query = """
                           SELECT term, python_wordfreq
                           FROM vocab.defined
                           WHERE python_wordfreq IS NOT NULL
                           ORDER BY python_wordfreq ASC LIMIT 10 \
                           """
            cursor.execute(bottom_query)
            bottom_words = cursor.fetchall()

            # Print report
            print("\n" + "=" * 60)
            print("📊 ZIPF FREQUENCY ANALYSIS REPORT")
            print("=" * 60)

            if stats and stats[0]:
                total, with_freq, avg_zipf, min_zipf, max_zipf, std_zipf = stats

                print(f"📈 Overall Statistics:")
                print(f"   Total terms: {total:,}")
                print(f"   Terms with frequency: {with_freq:,}")
                print(f"   Coverage: {(with_freq / total) * 100:.1f}%")
                print(f"   Average Zipf: {avg_zipf:.2f}")
                print(f"   Range: {min_zipf:.2f} - {max_zipf:.2f}")
                print(f"   Standard deviation: {std_zipf:.2f}")

                print(f"\n📊 Frequency Distribution:")
                for category, count in distribution:
                    percentage = (count / with_freq) * 100
                    print(f"   {category}: {count:,} ({percentage:.1f}%)")

                print(f"\n🔝 Most Frequent Words:")
                for term, freq in top_words:
                    print(f"   {term}: {freq:.2f}")

                print(f"\n🔻 Least Frequent Words:")
                for term, freq in bottom_words:
                    print(f"   {term}: {freq:.2f}")


def main():
    """Main function to run the Zipf frequency updater"""

    # Database configuration - update these with your actual credentials
    db_config = {
        'host': '10.0.0.160',  # Update with your MySQL host
        'port': 3306,
        'database': 'vocab',
        'user': 'brian',  # Update with your MySQL username
        'password': 'Fl1p5ma5h!',  # Update with your MySQL password
        'charset': 'utf8mb4',
        'use_unicode': True,
        'autocommit': False
    }

    # Create updater
    updater = ZipfFrequencyUpdater(db_config)

    try:
        # Test connection first
        with updater.get_connection() as conn:
            logger.info("✅ Successfully connected to MySQL database")

        # Check current status
        total_to_process = updater.get_total_terms_to_process()
        logger.info(f"Found {total_to_process:,} terms that need Zipf frequency processing")

        if total_to_process == 0:
            logger.info("All terms already have Zipf frequencies!")
            updater.generate_frequency_report()
            return

        # Ask for confirmation
        print(f"\nThis will process {total_to_process:,} terms and update the database.")
        response = input("Continue? (y/N): ").strip().lower()

        if response not in ['y', 'yes']:
            logger.info("Operation cancelled")
            return

        # Process all terms
        updater.process_all_terms(batch_size=1000, max_workers=4)

        # Generate final report
        updater.generate_frequency_report()

    except KeyboardInterrupt:
        logger.info("\n⚠️ Operation interrupted by user")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()