#!/usr/bin/env python3
"""
Reset all ngram_freq scores to NULL in the defined table.
This prepares for a complete repopulation with the fixed ngram lookup.
"""

import pymysql
from core.config import VocabularyConfig

def reset_ngram_frequencies():
    """Reset all ngram_freq values to NULL."""
    print("Resetting all ngram_freq scores to NULL...")

    # Connect to database
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        # First, check current status
        cursor.execute("SELECT COUNT(*) FROM defined WHERE ngram_freq IS NOT NULL")
        current_count = cursor.fetchone()[0]
        print(f"Currently {current_count:,} records have ngram_freq values")

        # Reset all to NULL
        cursor.execute("UPDATE defined SET ngram_freq = NULL")
        updated_count = cursor.rowcount

        conn.commit()
        print(f"Reset {updated_count:,} records to ngram_freq = NULL")

        # Verify the reset
        cursor.execute("SELECT COUNT(*) FROM defined WHERE ngram_freq IS NULL")
        null_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM defined")
        total_count = cursor.fetchone()[0]

        print(f"Verification: {null_count:,} records now have ngram_freq = NULL out of {total_count:,} total")

        return True

    except Exception as e:
        print(f"ERROR: {e}")
        conn.rollback()
        return False

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    success = reset_ngram_frequencies()
    if success:
        print("✓ Reset completed successfully!")
    else:
        print("✗ Reset failed!")