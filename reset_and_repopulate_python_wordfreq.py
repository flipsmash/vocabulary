#!/usr/bin/env python3
"""
Reset python_wordfreq field to NULL and repopulate for ALL terms using wordfreq library.
Set -999 for terms not found in wordfreq.
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

def reset_python_wordfreq():
    """Reset all python_wordfreq values to NULL."""
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        cursor.execute("UPDATE vocab.defined SET python_wordfreq = NULL")
        reset_count = cursor.rowcount
        conn.commit()

        print(f"Reset {reset_count:,} python_wordfreq values to NULL")
        return True

    except Exception as e:
        print(f"ERROR resetting python_wordfreq: {e}")
        conn.rollback()
        return False

    finally:
        cursor.close()
        conn.close()

def get_all_terms() -> List[Tuple[int, str]]:
    """Get all terms from defined table."""
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, term
            FROM vocab.defined
            WHERE (phrase IS NULL OR phrase = 0)
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

def populate_all_wordfreq():
    """Populate python_wordfreq for ALL terms."""
    print("=" * 60)
    print("Complete Python WordFreq Repopulation")
    print("=" * 60)

    # Install wordfreq if needed
    if not install_wordfreq():
        return False

    # Reset all values to NULL first
    if not reset_python_wordfreq():
        return False

    # Get all terms to process
    all_terms = get_all_terms()
    print(f"Found {len(all_terms):,} total terms to process")

    if not all_terms:
        print("No terms found to process!")
        return True

    # Process terms in batches
    batch_size = 100
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        processed_count = 0
        found_count = 0
        not_found_count = 0

        for i in range(0, len(all_terms), batch_size):
            batch = all_terms[i:i + batch_size]
            batch_found = 0
            batch_not_found = 0

            print(f"\nProcessing batch {i//batch_size + 1}/{(len(all_terms) + batch_size - 1)//batch_size}")
            print(f"  Terms {i+1} to {min(i + batch_size, len(all_terms))} of {len(all_terms):,}")

            for word_id, term in batch:
                score = get_wordfreq_score(term)

                if score > -999:
                    batch_found += 1
                    # Only print first few successes to avoid spam
                    if batch_found <= 5:
                        print(f"    {term}: {score:.3f}")
                else:
                    batch_not_found += 1

                # Update database
                cursor.execute(
                    "UPDATE vocab.defined SET python_wordfreq = %s WHERE id = %s",
                    (score, word_id)
                )

            # Commit batch
            conn.commit()
            processed_count += len(batch)
            found_count += batch_found
            not_found_count += batch_not_found

            print(f"  Batch results: {batch_found} found, {batch_not_found} not found")
            print(f"  Progress: {processed_count:,}/{len(all_terms):,} ({processed_count/len(all_terms)*100:.1f}%)")

        print(f"\nFinal Results:")
        print(f"  Total processed: {processed_count:,} terms")
        print(f"  Found in wordfreq: {found_count:,} terms")
        print(f"  Not found (-999): {not_found_count:,} terms")
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
        cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE python_wordfreq IS NULL")
        remaining_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE python_wordfreq IS NOT NULL")
        populated_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE python_wordfreq > -999")
        found_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE python_wordfreq = -999")
        not_found_count = cursor.fetchone()[0]

        print(f"\nVerification:")
        print(f"  Records with python_wordfreq: {populated_count:,}")
        print(f"  Records still NULL: {remaining_count}")
        print(f"  Found in wordfreq: {found_count:,}")
        print(f"  Not found (-999): {not_found_count:,}")

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
        success = populate_all_wordfreq()

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