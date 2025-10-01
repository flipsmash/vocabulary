#!/usr/bin/env python3
"""
Download and process OpenWebText data to create word frequency scores.
Replicates the Google ngram approach for internet-based text.
"""

import os
import sys
import gzip
import json
import requests
import subprocess
from collections import defaultdict, Counter
import math
from typing import Dict, Tuple

def install_required_libraries():
    """Install required libraries if not available."""
    required_libs = ['datasets', 'transformers']

    for lib in required_libs:
        try:
            __import__(lib)
            print(f"OK {lib} library already available")
        except ImportError:
            print(f"Installing {lib} library...")
            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', lib])
                print(f"OK {lib} library installed successfully")
            except subprocess.CalledProcessError as e:
                print(f"ERROR Failed to install {lib}: {e}")
                return False
    return True

def download_openwebtext_frequency_list():
    """Download pre-computed OpenWebText frequency data or process from scratch."""

    # First try to find existing frequency lists online
    frequency_urls = [
        # Pre-computed frequency lists (if available)
        "https://raw.githubusercontent.com/commoncrawl/gensim-data/master/word-frequencies-en.txt",
        "https://raw.githubusercontent.com/mozilla/voice-corpus-tool/master/corpus_data/en_word_freq.txt"
    ]

    for url in frequency_urls:
        try:
            print(f"Trying to download frequency list from: {url}")
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                with open("openwebtext_frequencies.txt", "w", encoding="utf-8") as f:
                    f.write(response.text)
                print(f"Downloaded frequency list successfully")
                return "openwebtext_frequencies.txt"
        except Exception as e:
            print(f"Failed to download from {url}: {e}")
            continue

    # If no pre-computed lists available, process OpenWebText dataset
    print("No pre-computed frequency lists found. Processing OpenWebText dataset...")
    return process_openwebtext_dataset()

def process_openwebtext_dataset():
    """Process OpenWebText dataset to extract word frequencies."""
    try:
        from datasets import load_dataset
        print("Loading OpenWebText dataset from Hugging Face...")

        # Load a subset of OpenWebText for frequency analysis
        dataset = load_dataset("openwebtext", split="train", streaming=True)

        word_counts = Counter()
        total_words = 0
        processed_docs = 0
        max_docs = 100000  # Process subset for reasonable processing time

        print(f"Processing up to {max_docs:,} documents...")

        for i, example in enumerate(dataset):
            if i >= max_docs:
                break

            text = example['text'].lower()
            # Simple tokenization (can be improved)
            words = text.split()

            # Filter to single words only (no spaces, basic cleanup)
            for word in words:
                # Remove punctuation and keep only alphabetic words
                clean_word = ''.join(c for c in word if c.isalpha())
                if clean_word and len(clean_word) > 1:
                    word_counts[clean_word] += 1
                    total_words += 1

            processed_docs += 1
            if processed_docs % 10000 == 0:
                print(f"  Processed {processed_docs:,} documents, {total_words:,} words, {len(word_counts):,} unique words")

        print(f"\nFinal stats:")
        print(f"  Documents processed: {processed_docs:,}")
        print(f"  Total words: {total_words:,}")
        print(f"  Unique words: {len(word_counts):,}")

        # Save frequency data
        frequency_file = "openwebtext_frequencies.txt"
        with open(frequency_file, "w", encoding="utf-8") as f:
            for word, count in word_counts.most_common():
                frequency = count / total_words
                f.write(f"{word}\t{count}\t{frequency}\n")

        print(f"Saved frequency data to {frequency_file}")
        return frequency_file

    except Exception as e:
        print(f"Error processing OpenWebText dataset: {e}")
        return None

def load_frequency_data(filename: str) -> Dict[str, Tuple[int, float]]:
    """Load frequency data from file."""
    frequencies = {}

    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 3:
                    word = parts[0]
                    count = int(parts[1])
                    freq = float(parts[2])
                    frequencies[word] = (count, freq)
                elif len(parts) == 2:
                    # Handle different formats
                    word = parts[0]
                    count = int(parts[1])
                    frequencies[word] = (count, 0.0)  # Will calculate later
    except Exception as e:
        print(f"Error loading frequency data: {e}")
        return {}

    # If frequencies weren't provided, calculate them
    if frequencies and all(freq == 0.0 for _, freq in frequencies.values()):
        total_count = sum(count for count, _ in frequencies.values())
        for word in frequencies:
            count, _ = frequencies[word]
            freq = count / total_count
            frequencies[word] = (count, freq)

    return frequencies

def get_openwebtext_score(word: str, frequencies: Dict[str, Tuple[int, float]]) -> float:
    """Get OpenWebText frequency score for a word (similar to ngram approach)."""
    word_lower = word.lower()

    if word_lower in frequencies:
        count, frequency = frequencies[word_lower]

        # Use similar scoring to Google ngrams: log10(frequency * scaling_factor)
        # Scale to make scores comparable to ngram scores
        if frequency > 0:
            # Use similar scaling as ngram approach
            score = math.log10(frequency * 1_000_000_000)  # Scale up for positive scores
            return score
        else:
            return -999
    else:
        return -999

def create_openwebtext_lookup(frequencies: Dict[str, Tuple[int, float]]) -> str:
    """Create a lookup file similar to the ngram approach."""

    # Group words by first letter for efficient lookup
    letter_groups = defaultdict(list)

    for word, (count, freq) in frequencies.items():
        if word and word[0].isalpha():
            first_letter = word[0].lower()
            score = get_openwebtext_score(word, frequencies)
            letter_groups[first_letter].append((word, score))

    # Sort each group by word for binary search
    for letter in letter_groups:
        letter_groups[letter].sort()

    # Save to compressed file
    output_file = "openwebtext_lookup.txt.gz"

    with gzip.open(output_file, 'wt', encoding='utf-8') as f:
        for letter in sorted(letter_groups.keys()):
            for word, score in letter_groups[letter]:
                f.write(f"{word}\t{score:.6f}\n")

    print(f"Created OpenWebText lookup file: {output_file}")
    print(f"  Contains {sum(len(words) for words in letter_groups.values()):,} words")

    return output_file

def main():
    """Main function to download and process OpenWebText frequency data."""
    print("=" * 60)
    print("OpenWebText Frequency Data Processor")
    print("=" * 60)

    # Install required libraries
    if not install_required_libraries():
        return False

    # Create data directory
    os.makedirs("openwebtext_data", exist_ok=True)
    os.chdir("openwebtext_data")

    # Download or process frequency data
    frequency_file = download_openwebtext_frequency_list()

    if not frequency_file or not os.path.exists(frequency_file):
        print("Failed to obtain frequency data")
        return False

    # Load frequency data
    print(f"Loading frequency data from {frequency_file}...")
    frequencies = load_frequency_data(frequency_file)

    if not frequencies:
        print("Failed to load frequency data")
        return False

    print(f"Loaded {len(frequencies):,} word frequencies")

    # Create lookup file
    lookup_file = create_openwebtext_lookup(frequencies)

    # Test with a few sample words
    print(f"\nTesting frequency lookup:")
    test_words = ["the", "hello", "python", "computer", "internet", "website"]

    for word in test_words:
        score = get_openwebtext_score(word, frequencies)
        print(f"  {word}: {score:.3f}")

    print(f"\nOpenWebText frequency processing completed!")
    print(f"Lookup file: {lookup_file}")

    return True

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1)