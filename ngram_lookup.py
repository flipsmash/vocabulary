#!/usr/bin/env python3
"""
Look up ngram frequencies for individual terms using the downloaded Google Books data.
This provides the same results as the ngram.py API but using local data.
"""

import os
import sys
import gzip
import math
import argparse
from typing import Dict, List, Optional, Set

def load_total_counts():
    """Load total counts data (same as the main processor)."""
    total_counts_path = "temp/total_counts"

    if not os.path.exists(total_counts_path):
        print(f"ERROR: {total_counts_path} not found")
        return None

    year_totals = {}
    with open(total_counts_path, 'r') as f:
        content = f.read()

    # Parse year,count,volume format
    import re
    pairs = re.findall(r'(\d{4})\s*,\s*([0-9]+)\s*,\s*[0-9]+', content)

    for ys, cs in pairs:
        year = int(ys)
        count = int(cs)
        if year in year_totals:
            year_totals[year] = max(year_totals[year], count)
        else:
            year_totals[year] = count

    return year_totals

def find_ngram_files():
    """Find downloaded ngram data files."""
    data_dir = "temp/ngram_data"

    if not os.path.exists(data_dir):
        print(f"ERROR: Ngram data directory not found: {data_dir}")
        print("Run download_ngram_data.py first to download the data")
        return None

    files = []
    for letter in "abcdefghijklmnopqrstuvwxyz":
        filename = f"googlebooks-eng-all-1gram-20120701-{letter}.gz"
        filepath = os.path.join(data_dir, filename)
        if os.path.exists(filepath):
            files.append(filepath)

    if not files:
        print(f"ERROR: No ngram data files found in {data_dir}")
        return None

    return files

def lookup_terms(terms: List[str], year_start: int = 1900, year_end: int = 2019,
                aggregator: str = "mean", alpha: float = 1e-6, verbose: bool = False) -> Dict[str, Optional[float]]:
    """Look up ngram frequencies for the given terms."""

    # Load total counts
    year_totals = load_total_counts()
    if not year_totals:
        return {}

    # Filter to our year range
    valid_years = [y for y in range(year_start, year_end + 1) if y in year_totals]
    valid_years_set = set(valid_years)

    if verbose:
        print(f"Using years {year_start}-{year_end} ({len(valid_years)} years)")

    # Find ngram files
    ngram_files = find_ngram_files()
    if not ngram_files:
        return {}

    # Normalize search terms and group by first letter
    search_terms = {term.lower().strip() for term in terms if term.strip()}
    if not search_terms:
        return {}

    # Group terms by first letter for efficient searching
    terms_by_letter = {}
    for term in search_terms:
        first_letter = term[0] if term else 'a'
        if first_letter not in terms_by_letter:
            terms_by_letter[first_letter] = set()
        terms_by_letter[first_letter].add(term)

    if verbose:
        print(f"Searching for: {', '.join(search_terms)}")
        print(f"Grouped by letters: {list(terms_by_letter.keys())}")

    # Initialize word counts
    word_counts = {word: {year: 0 for year in valid_years} for word in search_terms}
    found_words = set()

    # Process only relevant ngram files (based on first letter)
    for filepath in ngram_files:
        filename = os.path.basename(filepath)
        letter = filename.split('-')[-1].replace('.gz', '')

        # Skip files that don't contain any of our terms
        if letter not in terms_by_letter:
            continue

        relevant_terms = terms_by_letter[letter]
        if verbose:
            print(f"Searching file {letter}.gz for: {', '.join(relevant_terms)}")

        try:
            with gzip.open(filepath, 'rt', encoding='utf-8') as f:
                lines_processed = 0
                local_found = set()

                for line in f:
                    lines_processed += 1

                    if verbose and lines_processed % 2000000 == 0:
                        print(f"  Processed {lines_processed:,} lines, found {len(local_found)} words in this file")

                    parts = line.strip().split('\t')
                    if len(parts) < 4:
                        continue

                    word = parts[0].lower()

                    # Quick check if this word is one we're looking for
                    if word not in relevant_terms:
                        continue

                    try:
                        year = int(parts[1])
                        count = int(parts[2])
                    except ValueError:
                        continue

                    if year in valid_years_set:
                        word_counts[word][year] += count
                        found_words.add(word)
                        local_found.add(word)

                        # Note: removed early exit - we need to read the entire file
                        # to get all year counts for each word

                if verbose:
                    print(f"  Found {len(local_found)} words in {letter}.gz: {', '.join(local_found)}")

        except Exception as e:
            if verbose:
                print(f"  Error processing {filepath}: {e}")

        # If we found all words overall, no need to check more files
        if len(found_words) == len(search_terms):
            if verbose:
                print(f"Found all {len(search_terms)} words, stopping file search")
            break

    if verbose:
        print(f"Found data for {len(found_words)}/{len(search_terms)} words")

    # Compute Zipf scores
    results = {}

    for word in search_terms:
        yearly_counts = word_counts[word]
        yearly_zipfs = []

        if verbose:
            total_count = sum(yearly_counts.values())
            print(f"\nDEBUG: Processing '{word}' - total count across all years: {total_count:,}")

        for year, count in yearly_counts.items():
            total_words = year_totals[year]
            relative_freq = (count + alpha) / total_words
            zipf = math.log10(relative_freq * 1_000_000) if relative_freq > 0 else float('-inf')

            if zipf != float('-inf'):
                yearly_zipfs.append(zipf)

            # Debug output for first few years or if verbose and count > 0
            if verbose and (count > 0 or len(yearly_zipfs) < 5):
                print(f"  {year}: count={count:,}, total={total_words:,}, rel_freq={relative_freq:.2e}, zipf={zipf:.3f}")

        # Apply aggregation
        if yearly_zipfs:
            if aggregator == "mean":
                results[word] = sum(yearly_zipfs) / len(yearly_zipfs)
            elif aggregator == "max":
                results[word] = max(yearly_zipfs)
            else:
                results[word] = sum(yearly_zipfs) / len(yearly_zipfs)  # default to mean

            if verbose:
                print(f"  Final {aggregator} Zipf score: {results[word]:.3f} (from {len(yearly_zipfs)} years)")
        else:
            results[word] = None
            if verbose:
                print(f"  No valid Zipf scores found for '{word}'")

    return results

def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(description="Look up Google Books ngram frequencies for terms")
    parser.add_argument("terms", nargs="+", help="Words to look up")
    parser.add_argument("--years", default="1900-2019", help="Year range (YYYY-YYYY)")
    parser.add_argument("--agg", choices=["mean", "max"], default="mean", help="Aggregation method")
    parser.add_argument("--alpha", type=float, default=1e-6, help="Smoothing parameter")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--format", choices=["simple", "detailed"], default="simple", help="Output format")

    args = parser.parse_args()

    # Parse year range
    try:
        year_start, year_end = map(int, args.years.split('-'))
    except ValueError:
        print("ERROR: Invalid year format. Use YYYY-YYYY (e.g., 1900-2019)")
        sys.exit(1)

    # Look up terms
    results = lookup_terms(
        args.terms,
        year_start=year_start,
        year_end=year_end,
        aggregator=args.agg,
        alpha=args.alpha,
        verbose=args.verbose
    )

    # Output results
    if args.format == "detailed":
        print(f"\nGoogle Books Ngram Frequencies ({year_start}-{year_end}, {args.agg}):")
        print("-" * 50)

        for term in args.terms:
            original_term = term
            norm_term = term.lower().strip()
            freq = results.get(norm_term)

            if freq is not None:
                print(f"{original_term:20} {freq:8.3f}")
            else:
                print(f"{original_term:20} {'NOT FOUND':>8}")
    else:
        # Simple format (same as ngram.py)
        for term in args.terms:
            norm_term = term.lower().strip()
            freq = results.get(norm_term)

            if freq is not None:
                print(f"{term}\t{freq:.3f}")
            else:
                print(f"{term}\t")

if __name__ == "__main__":
    main()