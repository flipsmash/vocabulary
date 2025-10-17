#!/usr/bin/env python3
"""
Download Google Books ngram data locally and process it the same way as the API.
This replicates exactly what ngram.py does but with local data.
"""

import os
import requests
import gzip
import math
from typing import Dict, Set
import time

def download_google_ngrams():
    """Download Google Books 1-gram data for English."""

    # Google provides 1-gram data in chunks
    # Format: http://storage.googleapis.com/books/ngrams/books/googlebooks-eng-all-1gram-20120701-[a-z].gz

    base_url = "http://storage.googleapis.com/books/ngrams/books/"
    data_dir = "temp/ngram_data"
    os.makedirs(data_dir, exist_ok=True)

    print("Downloading Google Books 1-gram data...")
    print("This will download ~4GB of data and take some time...")

    # Download files for each letter
    for letter in "abcdefghijklmnopqrstuvwxyz":
        filename = f"googlebooks-eng-all-1gram-20120701-{letter}.gz"
        url = base_url + filename
        local_path = os.path.join(data_dir, filename)

        if os.path.exists(local_path):
            print(f"  {filename} already exists, skipping...")
            continue

        print(f"  Downloading {filename}...")
        try:
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"  OK Downloaded {filename}")
            time.sleep(1)  # Be nice to Google's servers

        except Exception as e:
            print(f"  ERROR Failed to download {filename}: {e}")

    return data_dir

def load_total_counts():
    """Load total counts data (same as ngram.py uses)."""
    total_counts_path = "temp/total_counts"

    if not os.path.exists(total_counts_path):
        print(f"ERROR: {total_counts_path} not found")
        return None

    year_totals = {}
    with open(total_counts_path, 'r') as f:
        content = f.read()

    # Parse year,count,volume format (same logic as ngram.py)
    import re
    pairs = re.findall(r'(\d{4})\s*,\s*([0-9]+)\s*,\s*[0-9]+', content)

    for ys, cs in pairs:
        year = int(ys)
        count = int(cs)
        if year in year_totals:
            year_totals[year] = max(year_totals[year], count)
        else:
            year_totals[year] = count

    print(f"Loaded total counts for {len(year_totals)} years")
    return year_totals

def process_vocabulary_words(data_dir: str, vocabulary_words: Set[str], year_totals: Dict[int, int]):
    """Process downloaded ngram data for our vocabulary words."""

    # Filter to our year range (same as ngram.py)
    year_start, year_end = 1900, 2019
    valid_years = [y for y in range(year_start, year_end + 1) if y in year_totals]
    valid_years_set = set(valid_years)

    print(f"Processing years {year_start}-{year_end} ({len(valid_years)} years)")
    print(f"Looking for {len(vocabulary_words)} vocabulary words...")

    # Initialize word counts
    word_counts = {word: {year: 0 for year in valid_years} for word in vocabulary_words}
    found_words = set()

    # Process each downloaded file
    for letter in "abcdefghijklmnopqrstuvwxyz":
        filename = f"googlebooks-eng-all-1gram-20120701-{letter}.gz"
        filepath = os.path.join(data_dir, filename)

        if not os.path.exists(filepath):
            print(f"  Skipping {filename} (not found)")
            continue

        print(f"  Processing {filename}...")

        try:
            with gzip.open(filepath, 'rt', encoding='utf-8') as f:
                for line_num, line in enumerate(f):
                    if line_num % 1000000 == 0 and line_num > 0:
                        print(f"    Processed {line_num:,} lines, found {len(found_words)} words")

                    parts = line.strip().split('\t')
                    if len(parts) < 4:
                        continue

                    word = parts[0].lower()
                    try:
                        year = int(parts[1])
                        count = int(parts[2])
                    except ValueError:
                        continue

                    if year in valid_years_set and word in vocabulary_words:
                        word_counts[word][year] += count
                        found_words.add(word)

        except Exception as e:
            print(f"    Error processing {filename}: {e}")

    print(f"Found data for {len(found_words)}/{len(vocabulary_words)} words")
    return word_counts, found_words

def compute_zipf_scores(word_counts: Dict[str, Dict[int, int]], year_totals: Dict[int, int], alpha: float = 1e-6):
    """Compute Zipf scores exactly like ngram.py does."""

    zipf_scores = {}

    for word, yearly_counts in word_counts.items():
        yearly_zipfs = []

        for year, count in yearly_counts.items():
            total_words = year_totals[year]
            relative_freq = (count + alpha) / total_words
            zipf = math.log10(relative_freq * 1_000_000) if relative_freq > 0 else float('-inf')

            if zipf != float('-inf'):
                yearly_zipfs.append(zipf)

        # Use mean aggregation (same as ngram.py default)
        if yearly_zipfs:
            zipf_scores[word] = sum(yearly_zipfs) / len(yearly_zipfs)
        else:
            zipf_scores[word] = None

    return zipf_scores

def main():
    """Main execution."""
    print("=== Local Google Books Ngram Processor ===")

    # Load our vocabulary words
    import pymysql
    from core.config import VocabularyConfig

    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT DISTINCT LOWER(term)
            FROM vocab.defined
            WHERE ngram_freq IS NULL
            AND (phrase IS NULL OR phrase = 0)
            AND term NOT LIKE '% %'
        """)
        vocabulary_words = {row[0] for row in cursor.fetchall() if row[0]}
        print(f"Loaded {len(vocabulary_words)} vocabulary words from database")

    finally:
        cursor.close()
        conn.close()

    if not vocabulary_words:
        print("No words need processing!")
        return

    # Load total counts
    year_totals = load_total_counts()
    if not year_totals:
        return

    # Download ngram data
    data_dir = download_google_ngrams()

    # Process the data
    word_counts, found_words = process_vocabulary_words(data_dir, vocabulary_words, year_totals)

    # Compute Zipf scores
    zipf_scores = compute_zipf_scores(word_counts, year_totals)

    # Update database
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        updated_count = 0
        found_count = 0

        for word, score in zipf_scores.items():
            final_score = score if score is not None else -999
            if score is not None:
                found_count += 1

            cursor.execute("""
                UPDATE vocab.defined
                SET ngram_freq = %s
                WHERE LOWER(term) = %s AND ngram_freq IS NULL
            """, (final_score, word))
            updated_count += cursor.rowcount

        conn.commit()
        print(f"\nUpdated {updated_count} records")
        print(f"Found frequencies for {found_count}/{len(vocabulary_words)} words")
        print(f"Coverage: {found_count/len(vocabulary_words)*100:.1f}%")

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()