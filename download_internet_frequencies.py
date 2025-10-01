#!/usr/bin/env python3
"""
Download internet-based word frequency data from various online sources.
"""

import os
import requests
import gzip
import json
from collections import Counter, defaultdict
import math

def download_frequency_sources():
    """Try to download frequency data from various internet sources."""

    sources = [
        {
            "name": "English Web 2012 (Google Books)",
            "url": "https://storage.googleapis.com/books/ngrams/books/googlebooks-eng-fiction-1M-2gram-20120701-a.gz",
            "type": "ngram"
        },
        {
            "name": "COCA Frequency List",
            "url": "https://www.wordfrequency.info/samples/coca_5000.txt",
            "type": "simple"
        },
        {
            "name": "OpenSubtitles Frequency",
            "url": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/en/en_50k.txt",
            "type": "simple"
        },
        {
            "name": "Wikipedia Frequency",
            "url": "https://raw.githubusercontent.com/IlyaSemenenko/wikipedia-word-frequency/master/results/enwiki-2023-04-13.txt",
            "type": "simple"
        },
        {
            "name": "Reddit Frequency",
            "url": "https://raw.githubusercontent.com/rspeer/wordfreq/main/wordfreq/data/en.msgpack.gz",
            "type": "msgpack"
        }
    ]

    successful_downloads = []

    for source in sources:
        print(f"Trying to download: {source['name']}")
        try:
            response = requests.get(source['url'], timeout=60, stream=True)
            if response.status_code == 200:
                filename = f"freq_{source['name'].lower().replace(' ', '_')}.txt"

                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                print(f"  Downloaded: {filename} ({len(response.content):,} bytes)")
                successful_downloads.append({
                    "file": filename,
                    "source": source,
                    "size": len(response.content)
                })
            else:
                print(f"  Failed: HTTP {response.status_code}")

        except Exception as e:
            print(f"  Error: {e}")
            continue

    return successful_downloads

def process_simple_frequency_file(filename: str):
    """Process a simple word\tfrequency format file."""
    frequencies = {}

    try:
        with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f):
                if line_num > 100000:  # Limit processing for speed
                    break

                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                parts = line.split('\t') if '\t' in line else line.split()

                if len(parts) >= 2:
                    word = parts[0].lower()
                    try:
                        # Try different frequency formats
                        freq_val = parts[1]
                        if '.' in freq_val:
                            frequency = float(freq_val)
                        else:
                            count = int(freq_val)
                            # Convert count to frequency (will normalize later)
                            frequency = count

                        if word.isalpha() and len(word) > 1:
                            frequencies[word] = frequency

                    except ValueError:
                        continue

    except Exception as e:
        print(f"Error processing {filename}: {e}")
        return {}

    return frequencies

def normalize_frequencies(frequencies: dict) -> dict:
    """Normalize frequencies to log scale similar to ngram approach."""
    if not frequencies:
        return {}

    # Find if these are already frequencies (0-1) or counts (large numbers)
    max_val = max(frequencies.values())

    if max_val <= 1.0:
        # Already frequencies
        total = 1.0
    else:
        # These are counts, normalize
        total = sum(frequencies.values())

    normalized = {}
    for word, freq in frequencies.items():
        if freq > 0:
            # Convert to frequency if needed
            if max_val > 1.0:
                frequency = freq / total
            else:
                frequency = freq

            # Convert to log scale similar to ngram scores
            score = math.log10(frequency * 1_000_000_000)  # Scale for positive scores
            normalized[word] = score
        else:
            normalized[word] = -999

    return normalized

def create_lookup_file(frequencies: dict, output_name: str):
    """Create compressed lookup file."""
    if not frequencies:
        return None

    # Group by first letter
    letter_groups = defaultdict(list)

    for word, score in frequencies.items():
        if word and word[0].isalpha():
            first_letter = word[0].lower()
            letter_groups[first_letter].append((word, score))

    # Sort each group
    for letter in letter_groups:
        letter_groups[letter].sort()

    # Save to compressed file
    output_file = f"{output_name}_lookup.txt.gz"

    with gzip.open(output_file, 'wt', encoding='utf-8') as f:
        for letter in sorted(letter_groups.keys()):
            for word, score in letter_groups[letter]:
                f.write(f"{word}\t{score:.6f}\n")

    word_count = sum(len(words) for words in letter_groups.values())
    print(f"Created lookup file: {output_file} ({word_count:,} words)")

    return output_file

def main():
    """Main function."""
    print("=" * 60)
    print("Internet-Based Frequency Data Downloader")
    print("=" * 60)

    # Create data directory
    os.makedirs("internet_freq_data", exist_ok=True)
    os.chdir("internet_freq_data")

    # Download frequency sources
    downloads = download_frequency_sources()

    if not downloads:
        print("No frequency data sources were successfully downloaded")
        return False

    print(f"\nProcessing {len(downloads)} downloaded files...")

    best_source = None
    best_word_count = 0

    for download in downloads:
        filename = download['file']
        source_name = download['source']['name']

        print(f"\nProcessing: {source_name}")

        # Process the file
        frequencies = process_simple_frequency_file(filename)

        if frequencies:
            print(f"  Raw frequencies: {len(frequencies):,} words")

            # Normalize to log scale
            normalized = normalize_frequencies(frequencies)
            print(f"  Normalized: {len(normalized):,} words")

            # Create lookup file
            lookup_file = create_lookup_file(normalized, source_name.lower().replace(' ', '_'))

            # Test with sample words
            test_words = ["the", "hello", "computer", "internet"]
            print(f"  Sample scores:")
            for word in test_words:
                if word in normalized:
                    print(f"    {word}: {normalized[word]:.3f}")

            # Track best source
            if len(frequencies) > best_word_count:
                best_word_count = len(frequencies)
                best_source = {
                    "name": source_name,
                    "file": lookup_file,
                    "count": len(frequencies)
                }
        else:
            print(f"  Failed to process {filename}")

    if best_source:
        print(f"\nBest source: {best_source['name']} ({best_source['count']:,} words)")
        print(f"Lookup file: {best_source['file']}")

        # Copy best source to standard name
        import shutil
        shutil.copy(best_source['file'], "internet_frequencies.txt.gz")
        print("Copied best source to: internet_frequencies.txt.gz")

        return True
    else:
        print("No usable frequency data found")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1)