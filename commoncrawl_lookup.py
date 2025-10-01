#!/usr/bin/env python3
"""
Look up word frequency in Common Crawl data.
Replicates the ngram_lookup.py approach for Common Crawl web data.
"""

import gzip
import argparse
from typing import Optional

def get_commoncrawl_frequency(word: str, data_file: str = "commoncrawl_data/fasttext_commoncrawl_lookup.txt.gz") -> float:
    """
    Look up a word's frequency in Common Crawl data.
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
        print(f"ERROR: Common Crawl data file not found: {data_file}")
        print("Run download_commoncrawl_frequencies.py first to create the lookup file")
        return -999
    except Exception as e:
        print(f"ERROR reading Common Crawl data: {e}")
        return -999

def test_lookup():
    """Test the lookup function with sample words."""
    test_words = [
        # Modern/digital words that should be higher in Common Crawl
        "internet", "website", "computer", "digital", "online", "software",
        "smartphone", "app", "download", "email", "blog", "social",

        # Traditional words for comparison
        "the", "hello", "world", "house", "book", "water",

        # Rare/specialized terms
        "xenodocheionology", "sesquipedalian", "pulchritude"
    ]

    print("Testing Common Crawl frequency lookup:")
    print("=" * 50)

    for word in test_words:
        score = get_commoncrawl_frequency(word)
        if score > -999:
            print(f"{word:20s}: {score:8.3f}")
        else:
            print(f"{word:20s}: NOT FOUND")

def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(description="Look up word frequency in Common Crawl data")
    parser.add_argument("word", nargs="?", help="Word to look up")
    parser.add_argument("--test", action="store_true", help="Run test with sample words")
    parser.add_argument("--data-file", default="commoncrawl_data/fasttext_commoncrawl_lookup.txt.gz",
                       help="Path to Common Crawl lookup file")

    args = parser.parse_args()

    if args.test:
        test_lookup()
    elif args.word:
        score = get_commoncrawl_frequency(args.word, args.data_file)
        if score > -999:
            print(f"{args.word}: {score:.6f}")
        else:
            print(f"{args.word}: NOT FOUND")
    else:
        print("Usage: python commoncrawl_lookup.py <word> [--data-file FILE]")
        print("   or: python commoncrawl_lookup.py --test")

if __name__ == "__main__":
    main()