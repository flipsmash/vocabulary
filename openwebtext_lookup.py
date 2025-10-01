#!/usr/bin/env python3
"""
Look up word frequency in OpenWebText data.
Replicates the ngram_lookup.py approach for OpenWebText data.
"""

import gzip
import math
import argparse
from typing import Optional

def get_openwebtext_frequency(word: str, data_file: str = "openwebtext_data/openwebtext_lookup.txt.gz") -> float:
    """
    Look up a word's frequency in OpenWebText data.
    Returns the frequency score or -999 if not found.
    """

    word_lower = word.lower().strip()

    if not word_lower or not word_lower.isalpha():
        return -999

    try:
        with gzip.open(data_file, 'rt', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                parts = line.split('\t')
                if len(parts) >= 2:
                    file_word = parts[0]
                    score = float(parts[1])

                    if file_word == word_lower:
                        return score

        # Word not found
        return -999

    except FileNotFoundError:
        print(f"ERROR: OpenWebText data file not found: {data_file}")
        print("Run download_openwebtext_data.py first to create the lookup file")
        return -999
    except Exception as e:
        print(f"ERROR reading OpenWebText data: {e}")
        return -999

def test_lookup():
    """Test the lookup function with sample words."""
    test_words = [
        "the", "hello", "world", "python", "computer",
        "internet", "website", "technology", "data",
        "xenodocheionology", "sesquipedalian", "pulchritude"
    ]

    print("Testing OpenWebText frequency lookup:")
    print("-" * 40)

    for word in test_words:
        score = get_openwebtext_frequency(word)
        if score > -999:
            print(f"{word:20s}: {score:8.3f}")
        else:
            print(f"{word:20s}: NOT FOUND")

def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(description="Look up word frequency in OpenWebText data")
    parser.add_argument("word", nargs="?", help="Word to look up")
    parser.add_argument("--test", action="store_true", help="Run test with sample words")
    parser.add_argument("--data-file", default="openwebtext_data/openwebtext_lookup.txt.gz",
                       help="Path to OpenWebText lookup file")

    args = parser.parse_args()

    if args.test:
        test_lookup()
    elif args.word:
        score = get_openwebtext_frequency(args.word, args.data_file)
        if score > -999:
            print(f"{args.word}: {score:.6f}")
        else:
            print(f"{args.word}: NOT FOUND")
    else:
        print("Usage: python openwebtext_lookup.py <word> [--data-file FILE]")
        print("   or: python openwebtext_lookup.py --test")

if __name__ == "__main__":
    main()