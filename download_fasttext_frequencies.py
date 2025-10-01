#!/usr/bin/env python3
"""
Download and process FastText Common Crawl word vectors to extract frequency data.
FastText vectors are sorted by frequency, making them perfect for our needs.
"""

import os
import sys
import gzip
import requests
import math
from collections import defaultdict
from typing import Dict, List, Tuple

def download_fasttext_vectors():
    """Download FastText Common Crawl vectors for English."""

    # FastText vectors URL (trained on Common Crawl + Wikipedia)
    fasttext_url = "https://dl.fbaipublicfiles.com/fasttext/vectors-crawl/cc.en.300.vec.gz"

    print("Downloading FastText Common Crawl vectors...")
    print("Note: This file is ~650MB compressed, ~4GB uncompressed")
    print(f"URL: {fasttext_url}")

    filename = "cc.en.300.vec.gz"

    try:
        # Check if file exists first
        response = requests.head(fasttext_url, timeout=30)
        if response.status_code != 200:
            print(f"File not found (HTTP {response.status_code})")
            return None

        file_size = int(response.headers.get('content-length', 0))
        print(f"File size: {file_size:,} bytes ({file_size/1024/1024:.1f} MB)")

        # Download the file
        print("Downloading...")
        response = requests.get(fasttext_url, timeout=600, stream=True)

        downloaded_size = 0
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded_size += len(chunk)

                # Show progress every 50MB
                if downloaded_size % (50 * 1024 * 1024) == 0:
                    progress = (downloaded_size / file_size) * 100
                    print(f"  Downloaded: {downloaded_size:,} bytes ({progress:.1f}%)")

        print(f"Successfully downloaded: {filename}")
        return filename

    except Exception as e:
        print(f"Error downloading FastText vectors: {e}")
        return None

def process_fasttext_vectors(filename: str) -> Dict[str, int]:
    """Process FastText vectors to extract word frequencies."""

    print(f"Processing {filename} to extract word frequencies...")

    word_ranks = {}
    total_lines = 0

    try:
        with gzip.open(filename, 'rt', encoding='utf-8', errors='ignore') as f:
            # Skip the first line (contains metadata: number of words and vector dimensions)
            first_line = f.readline()
            print(f"FastText metadata: {first_line.strip()}")

            for line_num, line in enumerate(f):
                # Limit processing for reasonable time (FastText has 2M words)
                if line_num >= 500000:  # Process 500K words (should be the most frequent)
                    print(f"Processed {line_num:,} words (stopping for demo)")
                    break

                if line_num % 50000 == 0 and line_num > 0:
                    print(f"  Processed {line_num:,} words")

                line = line.strip()
                if not line:
                    continue

                # FastText format: "word vector_values..."
                parts = line.split(' ')
                if len(parts) >= 2:
                    word = parts[0].lower().strip()

                    # Filter to single words only (alphabetic, reasonable length)
                    if (word.isalpha() and
                        2 <= len(word) <= 20):
                        # Since FastText words are sorted by frequency,
                        # we can use the line number as a frequency rank
                        word_ranks[word] = line_num + 1  # +1 because we're 0-indexed

                total_lines += 1

        print(f"Final processing stats:")
        print(f"  Total lines processed: {total_lines:,}")
        print(f"  Unique words extracted: {len(word_ranks):,}")

        return word_ranks

    except Exception as e:
        print(f"Error processing {filename}: {e}")
        return {}

def create_frequency_scores(word_ranks: Dict[str, int]) -> Dict[str, float]:
    """Convert word ranks to log-scale frequency scores."""

    if not word_ranks:
        return {}

    scores = {}
    total_words = len(word_ranks)

    print(f"Converting {total_words:,} word ranks to frequency scores...")

    for word, rank in word_ranks.items():
        # Convert rank to frequency score using Zipf's law approximation
        # Higher rank = lower frequency, so we use total_words - rank + 1
        frequency = (total_words - rank + 1) / total_words

        # Convert to log scale (similar to ngram approach)
        if frequency > 0:
            # Scale to make scores comparable to ngram scores
            score = math.log10(frequency * 1_000_000_000)
            scores[word] = score
        else:
            scores[word] = -999

    # Show score statistics
    if scores:
        score_values = [s for s in scores.values() if s > -999]
        if score_values:
            print(f"Score statistics:")
            print(f"  Score range: {min(score_values):.3f} to {max(score_values):.3f}")
            print(f"  Valid scores: {len(score_values):,}")

    return scores

def create_lookup_file(scores: Dict[str, float], output_name: str = "fasttext_commoncrawl_lookup.txt.gz"):
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
    test_words = ["the", "computer", "internet", "website", "digital", "online", "smartphone", "app"]

    for word in test_words:
        if word in scores:
            print(f"  {word}: {scores[word]:.3f}")

    return output_name

def main():
    """Main function."""
    print("=" * 60)
    print("FastText Common Crawl Frequency Data Processor")
    print("=" * 60)

    # Create data directory
    os.makedirs("commoncrawl_data", exist_ok=True)
    os.chdir("commoncrawl_data")

    # Download FastText vectors
    vector_file = download_fasttext_vectors()

    if not vector_file or not os.path.exists(vector_file):
        print("Failed to download FastText vectors")
        return False

    # Process vectors to extract frequency data
    word_ranks = process_fasttext_vectors(vector_file)

    if not word_ranks:
        print("Failed to extract word frequencies")
        return False

    # Convert to scores
    scores = create_frequency_scores(word_ranks)

    if not scores:
        print("Failed to create frequency scores")
        return False

    # Create lookup file
    lookup_file = create_lookup_file(scores)

    if lookup_file:
        print(f"\nFastText Common Crawl frequency processing completed!")
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