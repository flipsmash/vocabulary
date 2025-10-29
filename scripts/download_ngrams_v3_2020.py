#!/usr/bin/env python3
"""
Download Google Books Ngrams Version 3 (2020) dataset.

This script downloads the English 1-gram files from the Version 3 dataset
(released February 2020, covers data up to 2019).

Usage:
    python scripts/download_ngrams_v3_2020.py --output-dir temp/ngram_data_v3

    # Resume interrupted download
    python scripts/download_ngrams_v3_2020.py --output-dir temp/ngram_data_v3 --resume
"""

import argparse
import sys
import time
from pathlib import Path
from urllib.request import urlretrieve
from urllib.error import URLError


BASE_URL = "http://storage.googleapis.com/books/ngrams/books/20200217/eng"
TOTAL_FILES = 24  # Version 3 has 24 numbered files (00000-00023)


def download_with_progress(url: str, output_path: Path, resume: bool = False) -> bool:
    """
    Download a file with progress reporting.

    Args:
        url: URL to download
        output_path: Local path to save file
        resume: Whether to skip if file already exists

    Returns:
        True if downloaded, False if skipped
    """
    if resume and output_path.exists():
        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  ✓ Already exists ({file_size_mb:.1f} MB) - skipping")
        return False

    try:
        def report_progress(block_num, block_size, total_size):
            """Report download progress."""
            if total_size > 0:
                downloaded = block_num * block_size
                percent = min(100, (downloaded / total_size) * 100)
                mb_downloaded = downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)

                # Update progress on same line
                print(f"\r  Progress: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)",
                      end='', flush=True)

        print(f"  Downloading from {url}...")
        urlretrieve(url, output_path, reporthook=report_progress)
        print()  # New line after progress

        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  ✓ Downloaded ({file_size_mb:.1f} MB)")
        return True

    except URLError as e:
        print(f"\n  ✗ Error: {e}")
        if output_path.exists():
            output_path.unlink()  # Remove partial download
        return False
    except KeyboardInterrupt:
        print("\n  ✗ Download interrupted")
        if output_path.exists():
            output_path.unlink()  # Remove partial download
        raise


def download_ngrams_v3(output_dir: Path, resume: bool = False, delay: float = 1.0) -> None:
    """
    Download all English 1-gram files from Version 3 dataset.

    Args:
        output_dir: Directory to save downloaded files
        resume: Whether to skip already downloaded files
        delay: Delay between downloads in seconds (be nice to servers)
    """
    print("=" * 70)
    print("DOWNLOADING GOOGLE BOOKS NGRAMS VERSION 3 (2020)")
    print("=" * 70)
    print(f"Output directory: {output_dir}")
    print(f"Total files: {TOTAL_FILES} data files")
    print(f"Resume mode: {'ON' if resume else 'OFF'}")
    print()

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Skip totalcounts file - not available in same format for Version 3
    # We can compute total counts from the data files if needed
    print("[0/24] Note: Skipping totalcounts file (not available in Version 3)")
    print()

    # Download numbered data files
    downloaded_count = 0
    skipped_count = 0
    failed_count = 0

    for i in range(TOTAL_FILES):
        file_num = f"{i:05d}"
        print(f"[{i+1}/{TOTAL_FILES}] Downloading file {file_num}...")

        # Correct URL format for Version 3: http://storage.googleapis.com/books/ngrams/books/20200217/eng/1-00000-of-00024.gz
        url = f"{BASE_URL}/1-{file_num}-of-00024.gz"
        filename = f"googlebooks-eng-1-ngrams-20200217-1-{file_num}-of-00024.gz"
        output_path = output_dir / filename

        result = download_with_progress(url, output_path, resume)

        if result:
            downloaded_count += 1
        elif resume and output_path.exists():
            skipped_count += 1
        else:
            failed_count += 1

        print()

        # Be nice to Google's servers
        if i < TOTAL_FILES - 1:  # Don't delay after last file
            time.sleep(delay)

    # Summary
    print("=" * 70)
    print("DOWNLOAD COMPLETE")
    print("=" * 70)
    print(f"Downloaded: {downloaded_count} files")
    if skipped_count > 0:
        print(f"Skipped (already exist): {skipped_count} files")
    if failed_count > 0:
        print(f"Failed: {failed_count} files")
    print()
    print(f"Files saved to: {output_dir}")
    print()
    print("Next steps:")
    print("  1. Run the index builder:")
    print(f"     python scripts/build_complete_ngram_index.py \\")
    print(f"       --ngram-dir {output_dir} \\")
    print(f"       --output temp/word_frequencies_complete_v3.txt")
    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download Google Books Ngrams Version 3 (2020) dataset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("temp/ngram_data_v3"),
        help="Directory to save downloaded files (default: temp/ngram_data_v3)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip files that already exist (useful for resuming interrupted downloads)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between downloads in seconds (default: 1.0)"
    )

    args = parser.parse_args()

    try:
        download_ngrams_v3(args.output_dir, args.resume, args.delay)
    except KeyboardInterrupt:
        print("\n\nDownload interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
