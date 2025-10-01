#!/usr/bin/env python3
"""
Populate commoncrawl_freq field for all terms using Common Crawl (FastText) data.
Replicates the approach used for ngram_freq population.
"""

import sys
import pymysql
from typing import List, Tuple
from core.config import VocabularyConfig
from commoncrawl_lookup import get_commoncrawl_frequency

def check_database_schema():
    """Check if commoncrawl_freq column exists, create if needed."""
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        # Check if column exists
        cursor.execute("SHOW COLUMNS FROM defined LIKE 'commoncrawl_freq'")
        column_exists = cursor.fetchone() is not None

        if not column_exists:
            print("Adding commoncrawl_freq column to defined table...")
            cursor.execute("ALTER TABLE defined ADD COLUMN commoncrawl_freq DECIMAL(8,3) DEFAULT NULL")
            conn.commit()
            print("OK commoncrawl_freq column added")
        else:
            print("OK commoncrawl_freq column already exists")

        return True

    except Exception as e:
        print(f"ERROR checking/creating database schema: {e}")
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
            FROM defined
            WHERE (phrase IS NULL OR phrase = 0)
            AND term NOT LIKE '% %'
            ORDER BY id
        """)

        results = cursor.fetchall()
        return [(row[0], row[1].strip()) for row in results if row[1] and row[1].strip()]

    finally:
        cursor.close()
        conn.close()

def reset_commoncrawl_freq():
    """Reset all commoncrawl_freq values to NULL."""
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        cursor.execute("UPDATE defined SET commoncrawl_freq = NULL")
        reset_count = cursor.rowcount
        conn.commit()

        print(f"Reset {reset_count:,} commoncrawl_freq values to NULL")
        return True

    except Exception as e:
        print(f"ERROR resetting commoncrawl_freq: {e}")
        conn.rollback()
        return False

    finally:
        cursor.close()
        conn.close()

def populate_commoncrawl_frequencies():
    """Populate commoncrawl_freq for ALL terms."""
    print("=" * 60)
    print("Common Crawl Frequency Population")
    print("=" * 60)

    # Check/create database schema
    if not check_database_schema():
        return False

    # Reset all values to NULL first
    if not reset_commoncrawl_freq():
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
                score = get_commoncrawl_frequency(term)

                if score > -999:
                    batch_found += 1
                    # Only print first few successes to avoid spam
                    if batch_found <= 5:
                        print(f"    {term}: {score:.3f}")
                else:
                    batch_not_found += 1

                # Update database
                cursor.execute(
                    "UPDATE defined SET commoncrawl_freq = %s WHERE id = %s",
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
        print(f"  Found in Common Crawl: {found_count:,} terms")
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
    """Verify all records now have commoncrawl_freq values."""
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM defined WHERE commoncrawl_freq IS NULL")
        remaining_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM defined WHERE commoncrawl_freq IS NOT NULL")
        populated_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM defined WHERE commoncrawl_freq > -999")
        found_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM defined WHERE commoncrawl_freq = -999")
        not_found_count = cursor.fetchone()[0]

        print(f"\nVerification:")
        print(f"  Records with commoncrawl_freq: {populated_count:,}")
        print(f"  Records still NULL: {remaining_count}")
        print(f"  Found in Common Crawl: {found_count:,}")
        print(f"  Not found (-999): {not_found_count:,}")

        if remaining_count == 0:
            print("OK All records now have commoncrawl_freq values!")
        else:
            print(f"WARNING {remaining_count} records still need processing")

        return remaining_count == 0

    finally:
        cursor.close()
        conn.close()

def check_commoncrawl_status():
    """Check the current status of commoncrawl_freq population."""
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        # Check if column exists
        cursor.execute("SHOW COLUMNS FROM defined LIKE 'commoncrawl_freq'")
        column_exists = cursor.fetchone() is not None

        if not column_exists:
            print("commoncrawl_freq column does not exist yet")
            return

        # Check counts
        cursor.execute("SELECT COUNT(*) FROM defined")
        total_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM defined WHERE commoncrawl_freq IS NULL")
        null_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM defined WHERE commoncrawl_freq IS NOT NULL")
        populated_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM defined WHERE commoncrawl_freq > -999")
        found_count = cursor.fetchone()[0]

        print(f"Common Crawl Frequency Status:")
        print(f"  Total records: {total_count:,}")
        print(f"  NULL commoncrawl_freq: {null_count:,}")
        print(f"  Populated commoncrawl_freq: {populated_count:,}")
        print(f"  Found (> -999): {found_count:,}")

        if null_count > 0:
            print(f"  Need to process: {null_count:,} records")
        else:
            print(f"  All records have commoncrawl_freq values")

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        check_commoncrawl_status()
    else:
        try:
            success = populate_commoncrawl_frequencies()

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