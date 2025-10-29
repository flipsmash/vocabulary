#!/usr/bin/env python3
"""
Maintain obsolete/archaic word markings in the database.

This script finds words with NULL obsolete_or_archaic values and marks them
using high-confidence patterns (obsolete, archaic, no longer, antiquated, [Obs.]).

Designed to be run via cron for regular maintenance.

Usage:
    # Check and mark NULL obsolete_or_archaic values
    python scripts/maintain_obsolete_words.py

    # Dry run to see what would be marked
    python scripts/maintain_obsolete_words.py --dry-run

    # Silent mode (only errors to stderr, good for cron)
    python scripts/maintain_obsolete_words.py --silent

    # Force recheck ALL words (not just NULLs)
    python scripts/maintain_obsolete_words.py --force-recheck

    # Dry run with force recheck
    python scripts/maintain_obsolete_words.py --force-recheck --dry-run

Example cron setup (weekly on Sunday at 3 AM):
    0 3 * * 0 cd /path/to/vocabulary && /path/to/.venv/bin/python scripts/maintain_obsolete_words.py --silent >> /var/log/vocab_maintenance.log 2>&1
"""

import argparse
import sys
import re
from pathlib import Path
from typing import Tuple, List
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import psycopg
from core.secure_config import get_database_config


def check_obsolescence(definition: str) -> Tuple[bool, str]:
    """
    Check if a definition contains HIGH CONFIDENCE obsolescence indicators.

    Returns:
        (is_obsolete, confidence_level) where confidence_level is 'high' or 'none'
    """
    if not definition:
        return False, 'none'

    # HIGH CONFIDENCE patterns only
    high_patterns = [
        ('obsolete', re.compile(r'\bobsolete\b', re.IGNORECASE)),
        ('archaic', re.compile(r'\barchaic\b', re.IGNORECASE)),
        ('no longer', re.compile(r'\bno longer\b', re.IGNORECASE)),
        ('antiquated', re.compile(r'\bantiquated\b', re.IGNORECASE)),
        ('[Obs]', re.compile(r'\[Obs\.?\]')),  # [Obs.] or [Obs] in square brackets
    ]

    for name, pattern in high_patterns:
        if pattern.search(definition):
            return True, 'high'

    return False, 'none'


def maintain_obsolete_words(dry_run: bool = False, silent: bool = False, force_recheck: bool = False):
    """
    Find and mark words with NULL obsolete_or_archaic values.

    Args:
        dry_run: If True, preview changes without updating database
        silent: If True, suppress informational output
        force_recheck: If True, recheck ALL words regardless of current value
    """
    def log(message: str, is_error: bool = False):
        """Log message unless in silent mode."""
        if not silent or is_error:
            stream = sys.stderr if is_error else sys.stdout
            print(message, file=stream, flush=True)

    start_time = datetime.now()
    log(f"Starting obsolete word maintenance at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    config = get_database_config()

    conn = psycopg.connect(
        host=config.host,
        port=config.port,
        dbname=config.database,
        user=config.user,
        password=config.password,
        options=f'-c search_path={config.schema}'
    )

    cursor = conn.cursor()

    # Check if column exists
    log("\n1. Checking obsolete_or_archaic column...")
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'defined'
          AND column_name = 'obsolete_or_archaic'
    """, (config.schema,))

    column_info = cursor.fetchone()
    if not column_info:
        log("   Creating obsolete_or_archaic column...")
        if not dry_run:
            cursor.execute("""
                ALTER TABLE defined
                ADD COLUMN obsolete_or_archaic BOOLEAN DEFAULT FALSE
            """)
            conn.commit()
        log("   ✓ Column created as BOOLEAN")
    else:
        log(f"   ✓ Column exists as {column_info[1].upper()}")

    # Count NULL values or all words depending on force_recheck
    if force_recheck:
        log("\n2. Force recheck enabled - processing ALL words...")
        cursor.execute("""
            SELECT COUNT(*)
            FROM vocab.defined
            WHERE definition IS NOT NULL
        """)
        word_count = cursor.fetchone()[0]
        log(f"   Found {word_count:,} total words to check")
    else:
        log("\n2. Finding words with NULL obsolete_or_archaic...")
        cursor.execute("""
            SELECT COUNT(*)
            FROM vocab.defined
            WHERE obsolete_or_archaic IS NULL
              AND definition IS NOT NULL
        """)
        word_count = cursor.fetchone()[0]
        log(f"   Found {word_count:,} words with NULL obsolete_or_archaic")

    if word_count == 0 and not force_recheck:
        log("\n✓ All words have obsolete_or_archaic values set")
        cursor.close()
        conn.close()
        return

    # Get words to process
    log(f"\n3. Fetching definitions...")
    if force_recheck:
        cursor.execute("""
            SELECT id, term, definition, part_of_speech
            FROM vocab.defined
            WHERE definition IS NOT NULL
            ORDER BY id
        """)
    else:
        cursor.execute("""
            SELECT id, term, definition, part_of_speech
            FROM vocab.defined
            WHERE obsolete_or_archaic IS NULL
              AND definition IS NOT NULL
            ORDER BY id
        """)

    words_to_process = cursor.fetchall()
    log(f"   Retrieved {len(words_to_process):,} definitions")

    # Analyze each word
    log(f"\n4. Analyzing definitions for HIGH CONFIDENCE obsolescence markers...")
    log(f"   Mode: HIGH CONFIDENCE ONLY (obsolete, archaic, no longer, antiquated, [Obs.])")
    log(f"   Dry run: {'YES (no changes will be made)' if dry_run else 'NO (will update database)'}")

    obsolete_ids = []
    non_obsolete_ids = []
    obsolete_examples: List[Tuple[int, str, str, str]] = []

    for word_id, term, definition, pos in words_to_process:
        is_obsolete, confidence = check_obsolescence(definition)

        if is_obsolete and confidence == 'high':
            obsolete_ids.append(word_id)
            # Save first 5 examples
            if len(obsolete_examples) < 5:
                obsolete_examples.append((word_id, term, pos or 'TBD', definition[:100]))
        else:
            non_obsolete_ids.append(word_id)

    log(f"\n   Analysis results:")
    log(f"   - Obsolete/archaic (HIGH confidence): {len(obsolete_ids):,}")
    log(f"   - Non-obsolete: {len(non_obsolete_ids):,}")

    if obsolete_ids:
        log(f"\n   Example words that will be marked as obsolete:")
        for word_id, term, pos, def_preview in obsolete_examples:
            log(f"   - {term} ({pos}): {def_preview}...")

    if dry_run:
        log(f"\n[DRY RUN] Would mark {len(obsolete_ids):,} words as obsolete_or_archaic = TRUE")
        log(f"[DRY RUN] Would set {len(non_obsolete_ids):,} words as obsolete_or_archaic = FALSE")
    else:
        # Update database
        log(f"\n5. Updating database...")

        # Set obsolete words to TRUE
        if obsolete_ids:
            cursor.execute("""
                UPDATE vocab.defined
                SET obsolete_or_archaic = TRUE
                WHERE id = ANY(%s)
            """, (obsolete_ids,))
            log(f"   ✓ Marked {len(obsolete_ids):,} words as obsolete_or_archaic = TRUE")

        # Set non-obsolete words to FALSE
        if non_obsolete_ids:
            cursor.execute("""
                UPDATE vocab.defined
                SET obsolete_or_archaic = FALSE
                WHERE id = ANY(%s)
            """, (non_obsolete_ids,))
            log(f"   ✓ Set {len(non_obsolete_ids):,} words as obsolete_or_archaic = FALSE")

        conn.commit()

        # Verify the update
        cursor.execute("""
            SELECT COUNT(*)
            FROM vocab.defined
            WHERE obsolete_or_archaic IS NULL
        """)
        remaining_nulls = cursor.fetchone()[0]
        log(f"   ✓ Verification: {remaining_nulls:,} NULL values remain")

    # Final statistics
    log(f"\n6. Summary statistics:")
    cursor.execute("""
        SELECT
            COUNT(*) FILTER (WHERE obsolete_or_archaic = TRUE) as obsolete_count,
            COUNT(*) FILTER (WHERE obsolete_or_archaic = FALSE) as non_obsolete_count,
            COUNT(*) FILTER (WHERE obsolete_or_archaic IS NULL) as null_count,
            COUNT(*) as total_count
        FROM vocab.defined
    """)
    stats = cursor.fetchone()
    log(f"   - Obsolete/archaic (TRUE):  {stats[0]:,}")
    log(f"   - Non-obsolete (FALSE):     {stats[1]:,}")
    log(f"   - NULL (unprocessed):       {stats[2]:,}")
    log(f"   - Total words:              {stats[3]:,}")
    log(f"   - Obsolete percentage:      {100.0 * stats[0] / stats[3]:.2f}%")

    cursor.close()
    conn.close()

    elapsed = (datetime.now() - start_time).total_seconds()
    log(f"\n{'=' * 80}")
    if dry_run:
        log(f"DRY RUN COMPLETE - No changes made to database")
    else:
        log(f"MAINTENANCE COMPLETE - Database updated successfully")
    log(f"Elapsed time: {elapsed:.1f} seconds")
    log(f"{'=' * 80}")


def main():
    parser = argparse.ArgumentParser(
        description='Maintain obsolete/archaic word markings',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/maintain_obsolete_words.py                      # Mark NULL obsolete_or_archaic values
  python scripts/maintain_obsolete_words.py --dry-run            # Preview without updating
  python scripts/maintain_obsolete_words.py --silent             # Silent mode for cron
  python scripts/maintain_obsolete_words.py --force-recheck      # Remark ALL words
  python scripts/maintain_obsolete_words.py --force-recheck --dry-run  # Preview full recheck
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without updating the database'
    )

    parser.add_argument(
        '--silent',
        action='store_true',
        help='Suppress informational output (only show errors)'
    )

    parser.add_argument(
        '--force-recheck',
        action='store_true',
        help='Recheck ALL words, not just those with NULL values'
    )

    args = parser.parse_args()

    try:
        maintain_obsolete_words(
            dry_run=args.dry_run,
            silent=args.silent,
            force_recheck=args.force_recheck
        )
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
