"""
Local N-gram frequency lookup module using pre-computed word_frequencies.txt file.

This module reads from a pre-computed word frequency index instead of scanning
through the large Google Books N-gram .gz files. It provides the getNgrams()
interface expected by maintain_rarity.py script.
"""

import math
from pathlib import Path
from typing import Dict, List, Optional


def _load_frequency_index(frequency_file: str) -> Dict[str, int]:
    """
    Load the pre-computed word frequency index.

    Args:
        frequency_file: Path to word_frequencies.txt file

    Returns:
        Dictionary mapping word (lowercase) to total occurrence count
    """
    frequencies: Dict[str, int] = {}

    with open(frequency_file, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) == 2:
                word = parts[0].lower().strip()
                try:
                    count = int(parts[1])
                    frequencies[word] = count
                except ValueError:
                    continue

    return frequencies


def _calculate_zipf_from_counts(
    word_counts: Dict[str, Optional[int]],
    total_corpus_size: int
) -> Dict[str, Optional[float]]:
    """
    Calculate Zipf scores from raw counts.

    Args:
        word_counts: {word: count} or {word: None if not found}
        total_corpus_size: Total number of tokens in the corpus

    Returns:
        Dictionary mapping word to Zipf score (or None if not found)
    """
    results: Dict[str, Optional[float]] = {}

    for word, count in word_counts.items():
        if count is None or count == 0:
            results[word] = None
        else:
            # Zipf score: log10(frequency per million tokens)
            rel_freq = count / total_corpus_size
            zipf = math.log10(rel_freq * 1_000_000)
            results[word] = zipf

    return results


def getNgrams(
    words: List[str],
    corpus: str = "eng_2019",
    startYear: int = 1900,
    endYear: int = 2019,
    smoothing: float = 0,
    caseInsensitive: bool = True,
    totalcounts_path: Optional[str] = None,
    year_start: int = 1900,
    year_end: int = 2019,
    aggregator: str = "mean",
) -> Dict[str, Optional[float]]:
    """
    Get N-gram Zipf scores for words using pre-computed frequency index.

    This implementation uses word_frequencies.txt which contains total counts
    across all years, so the year parameters are ignored.

    Args:
        words: List of words to score
        corpus: Corpus to use (ignored, always uses local frequency file)
        startYear: Start year (ignored in this implementation)
        endYear: End year (ignored in this implementation)
        smoothing: Smoothing parameter (ignored in this implementation)
        caseInsensitive: Whether to normalize case (always True)
        totalcounts_path: Path to total counts file (ignored, uses word_frequencies.txt)
        year_start: Start year (ignored in this implementation)
        year_end: End year (ignored in this implementation)
        aggregator: How to aggregate yearly scores (ignored in this implementation)

    Returns:
        Dictionary mapping words to their Zipf scores (or None if not found)
    """
    if not words:
        return {}

    # Find frequency index file (prefer complete index if available)
    script_dir = Path(__file__).parent

    # First try the complete index (all words, no threshold)
    frequency_file = script_dir / "word_frequencies_complete.txt"

    if not frequency_file.exists():
        # Fall back to the original index (~12K minimum threshold)
        frequency_file = script_dir / "word_frequencies.txt"

    if not frequency_file.exists():
        # Try current directory
        frequency_file = Path.cwd() / "word_frequencies_complete.txt"

    if not frequency_file.exists():
        frequency_file = Path.cwd() / "word_frequencies.txt"

    if not frequency_file.exists():
        # Try temp directory
        frequency_file = Path.cwd() / "temp" / "word_frequencies_complete.txt"

    if not frequency_file.exists():
        frequency_file = Path.cwd() / "temp" / "word_frequencies.txt"

    if not frequency_file.exists():
        # Return None for all words if we can't find any index
        return {word: None for word in words}

    # Load the frequency index (lazy load, could be cached for performance)
    try:
        frequency_index = _load_frequency_index(str(frequency_file))
    except Exception as e:
        # Return None for all words if we can't load the index
        return {word: None for word in words}

    # Calculate total corpus size (sum of all word counts)
    # According to word_frequencies.txt, total is approximately 468 billion tokens
    # We can compute this or use a constant
    total_corpus_size = sum(frequency_index.values())

    # Look up counts for our words
    word_counts: Dict[str, Optional[int]] = {}
    for word in words:
        normalized_word = word.lower().strip()
        word_counts[normalized_word] = frequency_index.get(normalized_word, None)

    # Calculate Zipf scores
    results = _calculate_zipf_from_counts(word_counts, total_corpus_size)

    return results
