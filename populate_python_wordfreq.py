#!/usr/bin/env python3
"""
Populate python_wordfreq field for NULL entries using the wordfreq library.
"""

import sys
import pymysql
from typing import List, Tuple
from core.config import VocabularyConfig

def install_wordfreq():
    """Install wordfreq if not available."""
    try:
        import wordfreq
        print("OK wordfreq library already available")
        return True
    except ImportError:
        print("Installing wordfreq library...")
        import subprocess
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'wordfreq'])
            print("OK wordfreq library installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"ERROR Failed to install wordfreq: {e}")
            return False

def get_words_needing_wordfreq() -> List[Tuple[int, str]]:
    """Get words that need python_wordfreq populated."""
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, term
            FROM defined
            WHERE python_wordfreq IS NULL
            AND (phrase IS NULL OR phrase = 0)
            AND term NOT LIKE '% %'
            ORDER BY id
        """)

        results = cursor.fetchall()
        return [(row[0], row[1].strip()) for row in results if row[1] and row[1].strip()]

    finally:
        cursor.close()
        conn.close()

def get_wordfreq_score(word: str) -> float:
    """Get wordfreq score for a word."""
    try:
        from wordfreq import word_frequency
        # Get frequency for English, with smoothing
        freq = word_frequency(word.lower(), 'en', wordlist='large')

        # Convert to log scale similar to Zipf but using different base
        # wordfreq returns frequency per word (0-1 scale)
        if freq > 0:
            # Convert to something similar to Zipf: log10(freq * 1_000_000)
            import math
            score = math.log10(freq * 1_000_000)
            return score
        else:
            return -999  # Not found
    except Exception as e:
        print(f"Error getting wordfreq for '{word}': {e}")
        return -999

def populate_wordfreq():
    """Populate python_wordfreq for all NULL entries."""
    print("=" * 60)
    print("Python WordFreq Populator")
    print("=" * 60)

    # Install wordfreq if needed
    if not install_wordfreq():
        return False

    # Get words needing processing
    words_to_process = get_words_needing_wordfreq()
    print(f"Found {len(words_to_process)} words needing python_wordfreq")

    if not words_to_process:
        print("No words need processing!")
        return True

    # Process words
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        processed_count = 0
        found_count = 0

        for word_id, term in words_to_process:
            score = get_wordfreq_score(term)

            if score > -999:
                found_count += 1
                print(f"  {term}: {score:.3f}")
            else:
                print(f"  {term}: NOT FOUND (-999)")

            # Update database
            cursor.execute(
                "UPDATE defined SET python_wordfreq = %s WHERE id = %s",
                (score, word_id)
            )
            processed_count += cursor.rowcount

        conn.commit()

        print(f"\nResults:")
        print(f"  Processed: {processed_count} words")
        print(f"  Found: {found_count} words")
        print(f"  Not found: {processed_count - found_count} words")
        print(f"  Success rate: {found_count/processed_count*100:.1f}%")

        return True

    except Exception as e:
        print(f"ERROR: {e}")
        conn.rollback()
        return False

    finally:
        cursor.close()
        conn.close()

def verify_completion():
    """Verify all records now have python_wordfreq values."""
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM defined WHERE python_wordfreq IS NULL")
        remaining_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM defined WHERE python_wordfreq IS NOT NULL")
        populated_count = cursor.fetchone()[0]

        print(f"\nVerification:")
        print(f"  Records with python_wordfreq: {populated_count:,}")
        print(f"  Records still NULL: {remaining_count}")

        if remaining_count == 0:
            print("OK All records now have python_wordfreq values!")
        else:
            print(f"WARNING {remaining_count} records still need processing")

        return remaining_count == 0

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    try:
        success = populate_wordfreq()

        if success:
            verify_completion()
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