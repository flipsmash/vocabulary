#!/usr/bin/env python3
"""
Analyze correlation between ngram_freq and python_wordfreq fields.
"""

import pymysql
import statistics
from core.config import VocabularyConfig

def analyze_correlation():
    """Analyze correlation between the two frequency measures."""
    conn = pymysql.connect(**VocabularyConfig.get_db_config())
    cursor = conn.cursor()

    try:
        # Get data where both frequencies are available (not -999)
        cursor.execute("""
            SELECT term, ngram_freq, python_wordfreq
            FROM vocab.defined
            WHERE ngram_freq > -999 AND python_wordfreq > -999
            ORDER BY ngram_freq DESC
        """)

        valid_pairs = cursor.fetchall()

        if not valid_pairs:
            print("No words with both frequency measures available!")
            return

        print(f"Found {len(valid_pairs)} words with both frequency measures")

        # Extract the frequency values
        ngram_freqs = [row[1] for row in valid_pairs]
        python_freqs = [row[2] for row in valid_pairs]

        # Calculate basic statistics
        print(f"\nNgram Frequency Stats:")
        print(f"  Min: {min(ngram_freqs):.3f}")
        print(f"  Max: {max(ngram_freqs):.3f}")
        print(f"  Mean: {statistics.mean(ngram_freqs):.3f}")
        print(f"  Median: {statistics.median(ngram_freqs):.3f}")

        print(f"\nPython WordFreq Stats:")
        print(f"  Min: {min(python_freqs):.3f}")
        print(f"  Max: {max(python_freqs):.3f}")
        print(f"  Mean: {statistics.mean(python_freqs):.3f}")
        print(f"  Median: {statistics.median(python_freqs):.3f}")

        # Calculate correlation coefficient (Pearson)
        def correlation(x, y):
            n = len(x)
            if n == 0:
                return 0

            mean_x = sum(x) / n
            mean_y = sum(y) / n

            numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
            sum_sq_x = sum((x[i] - mean_x) ** 2 for i in range(n))
            sum_sq_y = sum((y[i] - mean_y) ** 2 for i in range(n))

            denominator = (sum_sq_x * sum_sq_y) ** 0.5

            if denominator == 0:
                return 0

            return numerator / denominator

        corr_coeff = correlation(ngram_freqs, python_freqs)
        print(f"\nPearson Correlation Coefficient: {corr_coeff:.4f}")

        # Interpretation
        if abs(corr_coeff) > 0.8:
            strength = "very strong"
        elif abs(corr_coeff) > 0.6:
            strength = "strong"
        elif abs(corr_coeff) > 0.4:
            strength = "moderate"
        elif abs(corr_coeff) > 0.2:
            strength = "weak"
        else:
            strength = "very weak"

        direction = "positive" if corr_coeff > 0 else "negative"
        print(f"Correlation strength: {strength} {direction}")

        # Show some examples
        print(f"\nTop 10 words by Ngram frequency:")
        for i, (term, ngram, python) in enumerate(valid_pairs[:10]):
            print(f"  {i+1:2d}. {term:15s} | Ngram: {ngram:6.3f} | Python: {python:6.3f}")

        # Show words with biggest differences
        differences = [(abs(row[1] - row[2]), row[0], row[1], row[2]) for row in valid_pairs]
        differences.sort(reverse=True)

        print(f"\nTop 10 words with biggest frequency differences:")
        for i, (diff, term, ngram, python) in enumerate(differences[:10]):
            print(f"  {i+1:2d}. {term:15s} | Ngram: {ngram:6.3f} | Python: {python:6.3f} | Diff: {diff:.3f}")

        # Count how many words are found in each system
        cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE ngram_freq > -999")
        ngram_found = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM vocab.defined WHERE python_wordfreq > -999")
        python_found = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM vocab.defined")
        total_words = cursor.fetchone()[0]

        print(f"\nCoverage Comparison:")
        print(f"  Total words: {total_words:,}")
        print(f"  Ngram found: {ngram_found:,} ({ngram_found/total_words*100:.1f}%)")
        print(f"  Python found: {python_found:,} ({python_found/total_words*100:.1f}%)")
        print(f"  Both found: {len(valid_pairs):,} ({len(valid_pairs)/total_words*100:.1f}%)")

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Frequency Correlation Analysis")
    print("=" * 60)
    analyze_correlation()