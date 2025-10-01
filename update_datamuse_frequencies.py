#!/usr/bin/env python3
"""
Update frequency field in defined table using Datamuse API
"""

import mysql.connector
import requests
import time
import sys
from typing import Optional
from core.config import VocabularyConfig

def get_datamuse_frequency(word: str) -> Optional[float]:
    """
    Get word frequency from Datamuse API.
    Returns the frequency score or None if not available.
    """
    try:
        # Datamuse API endpoint for word frequency
        url = f"https://api.datamuse.com/words?sp={word}&md=f&max=1"

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        if data and len(data) > 0:
            # Check if the returned word matches exactly (case insensitive)
            if data[0].get('word', '').lower() == word.lower():
                # Extract frequency from tags
                tags = data[0].get('tags', [])
                for tag in tags:
                    if tag.startswith('f:'):
                        frequency_str = tag[2:]  # Remove 'f:' prefix
                        try:
                            return float(frequency_str)
                        except ValueError:
                            continue

        return None

    except (requests.RequestException, ValueError, KeyError) as e:
        print(f"Error fetching frequency for '{word}': {e}")
        return None

def update_frequencies_batch():
    """
    Update all terms in defined table that lack frequency data using Datamuse API
    """
    config = VocabularyConfig()
    conn = mysql.connector.connect(**config.get_db_config())
    cursor = conn.cursor()

    try:
        # Get all terms without frequency data
        cursor.execute("""
            SELECT id, term
            FROM defined
            WHERE frequency IS NULL
            ORDER BY id
        """)

        terms_to_update = cursor.fetchall()
        total_terms = len(terms_to_update)

        print(f"Found {total_terms} terms without frequency data")
        print("Starting Datamuse API updates...")

        updated_count = 0
        not_found_count = 0

        for i, (term_id, term) in enumerate(terms_to_update, 1):
            print(f"Processing {i}/{total_terms}: '{term}' (ID: {term_id})")

            # Get frequency from Datamuse
            frequency = get_datamuse_frequency(term)

            if frequency is not None:
                # Update with Datamuse frequency
                cursor.execute("""
                    UPDATE defined
                    SET frequency = %s
                    WHERE id = %s
                """, (frequency, term_id))
                updated_count += 1
                print(f"  Updated with frequency: {frequency}")
            else:
                # Set to -999 if no frequency available
                cursor.execute("""
                    UPDATE defined
                    SET frequency = -999
                    WHERE id = %s
                """, (term_id,))
                not_found_count += 1
                print(f"  No frequency found, set to -999")

            # Commit every 10 updates to avoid losing progress
            if i % 10 == 0:
                conn.commit()
                print(f"  Committed batch {i//10}")

            # Rate limiting: pause between requests to be respectful to API
            time.sleep(0.1)  # 100ms delay between requests

            # Longer pause every 100 requests
            if i % 100 == 0:
                print(f"  Pausing for rate limiting...")
                time.sleep(2.0)

        # Final commit
        conn.commit()

        print(f"\nUpdate complete!")
        print(f"Terms updated with Datamuse frequency: {updated_count}")
        print(f"Terms set to -999 (no frequency found): {not_found_count}")
        print(f"Total processed: {total_terms}")

    except Exception as e:
        print(f"Error during batch update: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def verify_updates():
    """
    Verify the frequency updates were successful
    """
    config = VocabularyConfig()
    conn = mysql.connector.connect(**config.get_db_config())
    cursor = conn.cursor()

    try:
        # Check updated statistics
        cursor.execute('SELECT COUNT(*) as total FROM defined')
        total = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) as null_freq FROM defined WHERE frequency IS NULL')
        null_freq = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) as has_freq FROM defined WHERE frequency IS NOT NULL AND frequency != -999')
        has_freq = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) as not_found FROM defined WHERE frequency = -999')
        not_found = cursor.fetchone()[0]

        print(f"\nVerification Results:")
        print(f"Total terms: {total}")
        print(f"Terms with NULL frequency: {null_freq}")
        print(f"Terms with valid frequency: {has_freq}")
        print(f"Terms with no frequency found (-999): {not_found}")

        # Sample of recently updated terms
        cursor.execute("""
            SELECT term, frequency
            FROM defined
            WHERE frequency IS NOT NULL
            ORDER BY id DESC
            LIMIT 10
        """)

        sample = cursor.fetchall()
        print(f"\nSample of recent frequency updates:")
        for term, freq in sample:
            print(f"  {term}: {freq}")

    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        verify_updates()
    elif len(sys.argv) > 1 and sys.argv[1] == "--auto":
        print("Starting Datamuse frequency update process in auto mode...")
        print("This will update all terms in the defined table that lack frequency data.")
        print("Terms will be updated with Datamuse API frequency or set to -999 if not found.")
        update_frequencies_batch()
        verify_updates()
    else:
        print("Starting Datamuse frequency update process...")
        print("This will update all terms in the defined table that lack frequency data.")
        print("Terms will be updated with Datamuse API frequency or set to -999 if not found.")

        response = input("Continue? (y/N): ")
        if response.lower() == 'y':
            update_frequencies_batch()
            verify_updates()
        else:
            print("Operation cancelled.")