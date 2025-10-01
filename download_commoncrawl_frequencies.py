#!/usr/bin/env python3
"""
Download and process Common Crawl frequency data from Stanford/UE corpus.
Creates lookup similar to Google ngram approach.
"""

import os
import sys
import gzip
import requests
import math
from collections import defaultdict, Counter
from typing import Dict, List, Tuple

def download_commoncrawl_data():
    """Download Common Crawl frequency data from statmt.org."""

    # URLs for Common Crawl data from Stanford/UE (current working URLs)
    base_url = "http://data.statmt.org/ngrams/raw/"

    # Try different Common Crawl files (these are very large, so we'll start with smaller ones)
    candidate_files = [
        "en.00.gz",  # English 1-grams, file 00
        "en.01.gz",  # English 1-grams, file 01
        "en.02.gz",  # English 1-grams, file 02
    ]

    print("Downloading Common Crawl frequency data from Stanford/UE corpus...")
    print("Note: These files are very large (GB each), downloading sample files first...")

    downloaded_files = []

    for filename in candidate_files:
        url = base_url + filename
        local_filename = f"cc_{filename.replace('/', '_')}"

        print(f"\nTrying to download: {filename}")
        print(f"URL: {url}")

        try:
            # Check if file exists first
            response = requests.head(url, timeout=30)
            if response.status_code != 200:
                print(f"  File not found (HTTP {response.status_code})")
                continue

            file_size = int(response.headers.get('content-length', 0))
            print(f"  File size: {file_size:,} bytes ({file_size/1024/1024:.1f} MB)")

            if file_size > 500 * 1024 * 1024:  # 500MB limit
                print(f"  Skipping - file too large for demo")
                continue

            # Download the file
            print(f"  Downloading...")
            response = requests.get(url, timeout=300, stream=True)

            with open(local_filename, 'wb') as f:
                downloaded_size = 0
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded_size += len(chunk)

                    # Show progress every 10MB
                    if downloaded_size % (10 * 1024 * 1024) == 0:
                        print(f"    Downloaded: {downloaded_size:,} bytes")

            print(f"  Successfully downloaded: {local_filename}")
            downloaded_files.append(local_filename)

            # For demo, just download one file
            break

        except Exception as e:
            print(f"  Error downloading {filename}: {e}")
            continue

    return downloaded_files

def process_commoncrawl_ngram_file(filename: str) -> Dict[str, int]:
    """Process a Common Crawl n-gram file to extract word frequencies."""

    word_counts = Counter()
    total_lines = 0

    print(f"Processing {filename}...")

    try:
        with gzip.open(filename, 'rt', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f):
                if line_num >= 1000000:  # Limit for demo
                    print(f"  Processed {line_num:,} lines (stopping for demo)")
                    break

                if line_num % 100000 == 0 and line_num > 0:
                    print(f"  Processed {line_num:,} lines, {len(word_counts):,} unique words")

                line = line.strip()
                if not line:
                    continue

                # Common Crawl format: "word\tcount\tother_info..."
                parts = line.split('\t')
                if len(parts) >= 2:
                    word = parts[0].lower().strip()
                    try:
                        count = int(parts[1])

                        # Filter to single words only (alphabetic, reasonable length)
                        if (word.isalpha() and
                            2 <= len(word) <= 20 and
                            count > 0):
                            word_counts[word] += count

                    except ValueError:
                        continue

                total_lines += 1

        print(f"Final processing stats:")
        print(f"  Total lines: {total_lines:,}")
        print(f"  Unique words: {len(word_counts):,}")
        print(f"  Total word count: {sum(word_counts.values()):,}")

        return dict(word_counts)

    except Exception as e:
        print(f"Error processing {filename}: {e}")
        return {}

def create_commoncrawl_scores(word_counts: Dict[str, int]) -> Dict[str, float]:
    """Convert word counts to log-scale scores similar to ngram approach."""

    if not word_counts:
        return {}

    total_count = sum(word_counts.values())
    scores = {}

    print(f"Converting {len(word_counts):,} words to frequency scores...")

    for word, count in word_counts.items():
        # Calculate frequency
        frequency = count / total_count

        # Convert to log scale (similar to ngram approach)
        if frequency > 0:
            # Use similar scaling as Google ngrams
            score = math.log10(frequency * 1_000_000_000)
            scores[word] = score
        else:
            scores[word] = -999

    print(f"Score statistics:")
    if scores:
        score_values = list(scores.values())
        score_values = [s for s in score_values if s > -999]
        if score_values:
            print(f"  Score range: {min(score_values):.3f} to {max(score_values):.3f}")
            print(f"  Valid scores: {len(score_values):,}")

    return scores

def create_lookup_file(scores: Dict[str, float], output_name: str = "commoncrawl_lookup.txt.gz"):
    """Create compressed lookup file similar to ngram approach."""

    if not scores:
        print("No scores to save")
        return None

    # Group by first letter for efficient lookup
    letter_groups = defaultdict(list)

    for word, score in scores.items():
        if word and word[0].isalpha():
            first_letter = word[0].lower()
            letter_groups[first_letter].append((word, score))

    # Sort each group
    for letter in letter_groups:
        letter_groups[letter].sort()

    # Save to compressed file
    total_words = 0

    with gzip.open(output_name, 'wt', encoding='utf-8') as f:
        for letter in sorted(letter_groups.keys()):
            for word, score in letter_groups[letter]:
                f.write(f"{word}\t{score:.6f}\n")
                total_words += 1

    print(f"Created lookup file: {output_name}")
    print(f"  Total words: {total_words:,}")

    # Test with sample words
    print(f"\nSample words from lookup:")
    test_words = ["the", "computer", "internet", "website", "digital", "online"]

    for word in test_words:
        if word in scores:
            print(f"  {word}: {scores[word]:.3f}")

    return output_name

def main():
    """Main function."""
    print("=" * 60)
    print("Common Crawl Frequency Data Processor")
    print("=" * 60)

    # Create data directory
    os.makedirs("commoncrawl_data", exist_ok=True)
    os.chdir("commoncrawl_data")

    # Download Common Crawl data
    downloaded_files = download_commoncrawl_data()

    if not downloaded_files:
        print("No Common Crawl files were downloaded")
        return False

    # Process the first downloaded file
    filename = downloaded_files[0]
    word_counts = process_commoncrawl_ngram_file(filename)

    if not word_counts:
        print("Failed to extract word frequencies")
        return False

    # Convert to scores
    scores = create_commoncrawl_scores(word_counts)

    if not scores:
        print("Failed to create frequency scores")
        return False

    # Create lookup file
    lookup_file = create_lookup_file(scores)

    if lookup_file:
        print(f"\nCommon Crawl frequency processing completed!")
        print(f"Lookup file: {lookup_file}")
        print(f"Use this file with commoncrawl_lookup.py for word lookups")
        return True
    else:
        print("Failed to create lookup file")
        return False

if __name__ == "__main__":
    try:
        success = main()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nDownload cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)