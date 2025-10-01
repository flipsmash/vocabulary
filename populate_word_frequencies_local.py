#!/usr/bin/env python3
"""
Populate word frequencies using local frequency data instead of Google ngrams API.
Uses word frequency lists that can be downloaded once and processed locally.
"""

import os
import sys
import requests
import pymysql
from typing import Dict, Optional
import math

def download_frequency_data():
    """Download a reliable word frequency list."""
    # Using Peter Norvig's frequency list (derived from Google Books)
    url = "https://norvig.com/ngrams/count_1w.txt"
    local_file = "temp/word_frequencies.txt"

    if os.path.exists(local_file):
        print(f"Frequency data already exists: {local_file}")
        return local_file

    print(f"Downloading word frequency data from {url}...")
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        with open(local_file, 'w', encoding='utf-8') as f:
            f.write(response.text)

        print(f"Downloaded frequency data to {local_file}")
        return local_file

    except Exception as e:
        print(f"Failed to download frequency data: {e}")
        return None

def load_word_frequencies(frequency_file: str) -> Dict[str, float]:
    """Load word frequencies and convert to Zipf scores."""
    frequencies = {}
    total_words = 0

    print(f"Loading frequencies from {frequency_file}...")

    with open(frequency_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            parts = line.split('\t')
            if len(parts) >= 2:
                word = parts[0].lower()
                try:
                    count = int(parts[1])
                    frequencies[word] = count
                    total_words += count
                except ValueError:
                    continue

    # Convert to Zipf scores (log10 of frequency per million words)
    zipf_scores = {}
    for word, count in frequencies.items():
        frequency_per_million = (count / total_words) * 1_000_000
        zipf_score = math.log10(frequency_per_million) if frequency_per_million > 0 else -999
        zipf_scores[word] = zipf_score

    print(f"Loaded {len(zipf_scores)} word frequencies")
    return zipf_scores

def populate_frequencies():
    """Main function to populate word frequencies in database."""
    from core.config import VocabularyConfig

    print("=" * 60)
    print("Word Frequency Populator (Local Data)")
    print("=" * 60)

    # Download/load frequency data
    frequency_file = download_frequency_data()
    if not frequency_file:
        print("ERROR: Could not obtain frequency data")
        return False

    word_frequencies = load_word_frequencies(frequency_file)
    if not word_frequencies:
        print("ERROR: No frequency data loaded")
        return False

    # Database setup
    db_config = VocabularyConfig.get_db_config()
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()

    try:
        # Get words that need frequency scores
        print("Getting words from database...")
        cursor.execute("""
            SELECT id, term
            FROM defined
            WHERE ngram_freq IS NULL
            AND (phrase IS NULL OR phrase = 0)
            ORDER BY id
        """)

        words_to_update = cursor.fetchall()
        print(f"Found {len(words_to_update)} words to update")

        if not words_to_update:
            print("No words need updating")
            return True

        # Update frequencies
        updated_count = 0
        found_count = 0

        for word_id, term in words_to_update:
            word_lower = term.lower().strip()
            frequency = word_frequencies.get(word_lower, -999)

            if frequency != -999:
                found_count += 1

            cursor.execute(
                "UPDATE defined SET ngram_freq = %s WHERE id = %s",
                (frequency, word_id)
            )
            updated_count += cursor.rowcount

        conn.commit()

        print(f"Updated {updated_count} records")
        print(f"Found frequencies for {found_count}/{len(words_to_update)} words")
        print(f"Set {len(words_to_update) - found_count} words to -999 (not found)")

        return True

    except Exception as e:
        print(f"ERROR: {e}")
        conn.rollback()
        return False

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    success = populate_frequencies()
    if success:
        print("Frequency population completed successfully!")
    else:
        print("Frequency population failed!")
        sys.exit(1)