#!/usr/bin/env python3
"""
Build a complete word frequency index from Google Books N-gram .gz files.

This script processes all the googlebooks-eng-all-1gram-*.gz files and creates
a comprehensive index of word frequencies, including even the rarest words.

OPTIMIZATIONS:
- Uses disk-based sorting with temporary files to handle millions of words
- Processes files alphabetically so same words are grouped together
- Merges partial results incrementally to keep memory usage low
"""

import gzip
import sys
import tempfile
import heapq
from pathlib import Path
from typing import Dict, List, Tuple, TextIO


def process_single_file(
    ngram_file: Path,
    temp_dir: Path,
    file_num: int,
    total_files: int
) -> Path:
    """
    Process a single ngram .gz file and write sorted word frequencies to a temp file.

    Args:
        ngram_file: Path to the .gz file to process
        temp_dir: Directory for temporary files
        file_num: Current file number (for progress)
        total_files: Total number of files

    Returns:
        Path to temporary output file containing sorted word frequencies
    """
    print(f"[{file_num}/{total_files}] Processing: {ngram_file.name}")

    # Accumulate frequencies for this file
    word_freqs: Dict[str, int] = {}
    lines_processed = 0

    try:
        with gzip.open(ngram_file, 'rt', encoding='utf-8', errors='ignore') as f:
            for line in f:
                lines_processed += 1

                if lines_processed % 5000000 == 0:
                    print(f"  {lines_processed:,} lines, {len(word_freqs):,} unique words in this file")

                # Parse: word TAB year TAB match_count TAB volume_count
                parts = line.strip().split('\t')
                if len(parts) < 3:
                    continue

                word = parts[0].strip().lower()
                if not word:
                    continue

                try:
                    count = int(parts[2])
                except (ValueError, IndexError):
                    continue

                # Accumulate counts for this word
                word_freqs[word] = word_freqs.get(word, 0) + count

        print(f"  Completed: {lines_processed:,} lines, {len(word_freqs):,} unique words")

        # Sort by word (alphabetically) and write to temp file
        temp_file = temp_dir / f"partial_{file_num:03d}.txt"
        print(f"  Writing sorted results to {temp_file.name}")

        with open(temp_file, 'w', encoding='utf-8') as out:
            for word in sorted(word_freqs.keys()):
                out.write(f"{word}\t{word_freqs[word]}\n")

        print(f"  Temp file created: {temp_file.name}")
        print()

        return temp_file

    except Exception as e:
        print(f"  ERROR: {e}")
        print()
        return None


def merge_sorted_files(
    temp_files: List[Path],
    output_file: Path,
    min_frequency: int = 1
) -> None:
    """
    Merge multiple sorted temporary files into final output using heap merge.

    This is memory-efficient as it only keeps one line per file in memory.

    Args:
        temp_files: List of sorted temporary files to merge
        output_file: Final output file
        min_frequency: Minimum frequency threshold
    """
    print(f"Merging {len(temp_files)} temporary files...")
    print(f"Output: {output_file}")
    print()

    # Open all temp files
    file_handles: List[TextIO] = []
    for tf in temp_files:
        if tf and tf.exists():
            file_handles.append(open(tf, 'r', encoding='utf-8'))

    if not file_handles:
        print("ERROR: No temp files to merge!")
        return

    # Initialize heap with first line from each file
    # Heap entries: (word, count, file_index)
    heap: List[Tuple[str, int, int]] = []

    for i, fh in enumerate(file_handles):
        line = fh.readline()
        if line:
            parts = line.strip().split('\t')
            if len(parts) == 2:
                word = parts[0]
                count = int(parts[1])
                heapq.heappush(heap, (word, count, i))

    # Merge sorted streams
    current_word = None
    current_count = 0
    words_written = 0

    with open(output_file, 'w', encoding='utf-8') as out:
        while heap:
            # Get smallest word from heap
            word, count, file_idx = heapq.heappop(heap)

            # If same word as current, accumulate count
            if word == current_word:
                current_count += count
            else:
                # Write previous word if it meets threshold
                if current_word is not None and current_count >= min_frequency:
                    out.write(f"{current_word}\t{current_count}\n")
                    words_written += 1

                    if words_written % 100000 == 0:
                        print(f"  Merged {words_written:,} words so far...")

                # Start new word
                current_word = word
                current_count = count

            # Read next line from same file
            line = file_handles[file_idx].readline()
            if line:
                parts = line.strip().split('\t')
                if len(parts) == 2:
                    next_word = parts[0]
                    next_count = int(parts[1])
                    heapq.heappush(heap, (next_word, next_count, file_idx))

        # Write final word
        if current_word is not None and current_count >= min_frequency:
            out.write(f"{current_word}\t{current_count}\n")
            words_written += 1

    # Close all file handles
    for fh in file_handles:
        fh.close()

    print(f"Merge complete! {words_written:,} words written to {output_file}")
    print()


def sort_output_by_frequency(input_file: Path, output_file: Path) -> None:
    """
    Sort the merged output by frequency (descending) instead of alphabetically.

    Args:
        input_file: Alphabetically sorted file
        output_file: Frequency-sorted output file
    """
    print("Sorting by frequency (descending)...")
    print(f"Reading from: {input_file}")
    print(f"Writing to: {output_file}")

    # Read all words and frequencies
    word_freqs: List[Tuple[int, str]] = []

    with open(input_file, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i % 100000 == 0 and i > 0:
                print(f"  Read {i:,} words...")

            parts = line.strip().split('\t')
            if len(parts) == 2:
                word = parts[0]
                count = int(parts[1])
                word_freqs.append((count, word))

    print(f"Total words read: {len(word_freqs):,}")
    print("Sorting...")

    # Sort by frequency (descending), then alphabetically for ties
    word_freqs.sort(reverse=True, key=lambda x: (x[0], x[1]))

    print("Writing sorted output...")

    with open(output_file, 'w', encoding='utf-8') as out:
        for count, word in word_freqs:
            out.write(f"{word}\t{count}\n")

    print(f"Frequency-sorted output written to: {output_file}")
    print(f"Most common: {word_freqs[0][1]} ({word_freqs[0][0]:,})")
    print(f"Least common: {word_freqs[-1][1]} ({word_freqs[-1][0]:,})")
    print()


def build_complete_index(
    ngram_dir: Path,
    output_file: Path,
    min_frequency: int = 1,
    keep_temp_files: bool = False
) -> None:
    """
    Build complete word frequency index using disk-based merge sort.

    Args:
        ngram_dir: Directory containing googlebooks-*.gz files
        output_file: Path to final output file
        min_frequency: Minimum frequency threshold
        keep_temp_files: Whether to keep temporary files after merging
    """
    print("=" * 70)
    print("BUILDING COMPLETE N-GRAM FREQUENCY INDEX")
    print("=" * 70)
    print(f"Source directory: {ngram_dir}")
    print(f"Output file: {output_file}")
    print(f"Minimum frequency: {min_frequency}")
    print()

    # Find all ngram files
    ngram_files = sorted(ngram_dir.glob('googlebooks-eng-all-1gram-*.gz'))

    if not ngram_files:
        print(f"ERROR: No ngram files found in {ngram_dir}")
        sys.exit(1)

    print(f"Found {len(ngram_files)} ngram files")
    print()

    # Create temp directory
    with tempfile.TemporaryDirectory(prefix='ngram_build_') as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        print(f"Using temporary directory: {temp_dir}")
        print()

        # Process each file and create sorted temp files
        print("PHASE 1: Processing individual files...")
        print("-" * 70)
        temp_files: List[Path] = []

        for i, ngram_file in enumerate(ngram_files, 1):
            temp_file = process_single_file(ngram_file, temp_dir, i, len(ngram_files))
            if temp_file:
                temp_files.append(temp_file)

        print("PHASE 1 COMPLETE")
        print(f"Created {len(temp_files)} temporary files")
        print()

        # Merge sorted temp files (alphabetically)
        print("PHASE 2: Merging sorted files...")
        print("-" * 70)
        alpha_sorted_file = temp_dir / "merged_alpha_sorted.txt"
        merge_sorted_files(temp_files, alpha_sorted_file, min_frequency)

        print("PHASE 2 COMPLETE")
        print()

        # Sort by frequency
        print("PHASE 3: Sorting by frequency...")
        print("-" * 70)
        sort_output_by_frequency(alpha_sorted_file, output_file)

        print("PHASE 3 COMPLETE")
        print()

    print("=" * 70)
    print("INDEX BUILD COMPLETE!")
    print("=" * 70)
    print(f"Output file: {output_file}")
    print(f"File size: {output_file.stat().st_size / (1024*1024):.1f} MB")
    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Build complete N-gram frequency index (memory-efficient)"
    )
    parser.add_argument(
        "--ngram-dir",
        type=Path,
        default=Path("ngram_data"),
        help="Directory containing googlebooks-*.gz files"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("word_frequencies_complete.txt"),
        help="Output file path"
    )
    parser.add_argument(
        "--min-freq",
        type=int,
        default=1,
        help="Minimum frequency threshold (default: 1)"
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary files after merging"
    )

    args = parser.parse_args()

    # Ensure output directory exists
    args.output.parent.mkdir(parents=True, exist_ok=True)

    build_complete_index(
        ngram_dir=args.ngram_dir,
        output_file=args.output,
        min_frequency=args.min_freq,
        keep_temp_files=args.keep_temp
    )
