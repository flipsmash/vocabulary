#!/usr/bin/env python3
"""
Mark obsolete/archaic words in the database based on definition analysis.

This script analyzes definitions for obsolescence indicators and updates
the obsolete_or_archaic field in the defined table.

HIGH CONFIDENCE markers (set to TRUE):
- "obsolete", "archaic", "no longer", "antiquated"
- [Obs.] or [Obs] in square brackets

MEDIUM CONFIDENCE markers (set to TRUE by default, use --high-only to exclude):
- "dated", "formerly" (without high confidence markers)

Usage:
    python scripts/mark_obsolete_words.py                # Mark both high and medium confidence
    python scripts/mark_obsolete_words.py --high-only    # Mark only high confidence
    python scripts/mark_obsolete_words.py --dry-run      # Preview without updating
"""

import argparse
import sys
import re
from pathlib import Path
from typing import Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import psycopg
from core.secure_config import get_database_config


def check_obsolescence(definition: str) -> Tuple[bool, str]:
    """
    Check if a definition contains obsolescence indicators.

    Returns:
        (is_obsolete, confidence_level) where confidence_level is 'high' or 'medium'
    """
    if not definition:
        return False, 'none'

    # HIGH CONFIDENCE patterns
    high_patterns = [
        ('obsolete', re.compile(r'obsolete', re.IGNORECASE)),
        ('archaic', re.compile(r'archaic', re.IGNORECASE)),
        ('no longer', re.compile(r'no longer', re.IGNORECASE)),
        ('antiquated', re.compile(r'antiquated', re.IGNORECASE)),
        ('[Obs]', re.compile(r'\[Obs\.?\]')),  # [Obs.] or [Obs] in square brackets
    ]

    for name, pattern in high_patterns:
        if pattern.search(definition):
            return True, 'high'

    # MEDIUM CONFIDENCE patterns (only if no high confidence markers found)
    medium_patterns = [
        ('dated', re.compile(r'dated', re.IGNORECASE)),
        ('formerly', re.compile(r'formerly', re.IGNORECASE)),
    ]

    for name, pattern in medium_patterns:
        if pattern.search(definition):
            return True, 'medium'

    return False, 'none'


def mark_obsolete_words(high_confidence_only: bool = False, dry_run: bool = False):
    """
    Mark obsolete/archaic words in the database.

    Args:
        high_confidence_only: If True, only mark high confidence obsolete words
        dry_run: If True, preview changes without updating database
    """
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

    # First, ensure the column exists
    print("Checking if obsolete_or_archaic column exists...")
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'defined'
          AND column_name = 'obsolete_or_archaic'
    """, (config.schema,))

    column_info = cursor.fetchone()
    if not column_info:
        print("Creating obsolete_or_archaic column...")
        if not dry_run:
            cursor.execute("""
                ALTER TABLE defined
                ADD COLUMN obsolete_or_archaic BOOLEAN DEFAULT FALSE
            """)
            conn.commit()
        print("✓ Column created as BOOLEAN")
    else:
        print(f"✓ Column already exists as {column_info[1].upper()}")

    # Get all definitions
    print("\nFetching all definitions...")
    cursor.execute("""
        SELECT id, term, definition, part_of_speech
        FROM vocab.defined
        WHERE definition IS NOT NULL
        ORDER BY id
    """)

    all_words = cursor.fetchall()
    print(f"Found {len(all_words):,} words with definitions")

    # Analyze each word
    print(f"\nAnalyzing definitions for obsolescence markers...")
    print(f"Mode: {'HIGH CONFIDENCE ONLY' if high_confidence_only else 'HIGH + MEDIUM CONFIDENCE'}")
    print(f"Dry run: {'YES (no changes will be made)' if dry_run else 'NO (will update database)'}\n")

    high_confidence_count = 0
    medium_confidence_count = 0
    obsolete_ids = []

    for word_id, term, definition, pos in all_words:
        is_obsolete, confidence = check_obsolescence(definition)

        if is_obsolete:
            if confidence == 'high':
                high_confidence_count += 1
                obsolete_ids.append(word_id)
            elif confidence == 'medium' and not high_confidence_only:
                medium_confidence_count += 1
                obsolete_ids.append(word_id)

    print(f"Analysis complete:")
    print(f"  High confidence obsolete: {high_confidence_count:,}")
    print(f"  Medium confidence obsolete: {medium_confidence_count:,}")
    print(f"  Total to mark as obsolete: {len(obsolete_ids):,}")
    print(f"  Percentage: {100.0 * len(obsolete_ids) / len(all_words):.2f}%")

    if dry_run:
        print("\n[DRY RUN] Would update database with these changes")

        # Show some examples
        print("\nExample HIGH CONFIDENCE words that would be marked:")
        cursor.execute("""
            SELECT term, part_of_speech,
                   substring(definition, 1, 100) as def_preview
            FROM vocab.defined
            WHERE definition ILIKE '%obsolete%'
               OR definition ILIKE '%archaic%'
               OR definition ~ '\\[Obs\\.?\\]'
            LIMIT 5
        """)
        for term, pos, def_preview in cursor.fetchall():
            print(f"  - {term} ({pos or 'TBD'}): {def_preview}...")

        if not high_confidence_only:
            print("\nExample MEDIUM CONFIDENCE words that would be marked:")
            cursor.execute("""
                SELECT term, part_of_speech,
                       substring(definition, 1, 100) as def_preview
                FROM vocab.defined
                WHERE (definition ILIKE '%dated%' OR definition ILIKE '%formerly%')
                  AND NOT (
                      definition ILIKE '%obsolete%'
                      OR definition ILIKE '%archaic%'
                      OR definition ~ '\\[Obs\\.?\\]'
                  )
                LIMIT 5
            """)
            for term, pos, def_preview in cursor.fetchall():
                print(f"  - {term} ({pos or 'TBD'}): {def_preview}...")
    else:
        # Update database
        print("\nUpdating database...")

        # First, reset all to FALSE
        cursor.execute("UPDATE vocab.defined SET obsolete_or_archaic = FALSE")

        # Then mark obsolete words as TRUE
        if obsolete_ids:
            cursor.execute("""
                UPDATE vocab.defined
                SET obsolete_or_archaic = TRUE
                WHERE id = ANY(%s)
            """, (obsolete_ids,))

        conn.commit()

        print(f"✓ Updated {len(obsolete_ids):,} words as obsolete/archaic")

        # Verify the update
        cursor.execute("""
            SELECT COUNT(*)
            FROM vocab.defined
            WHERE obsolete_or_archaic = TRUE
        """)
        verified_count = cursor.fetchone()[0]
        print(f"✓ Verified: {verified_count:,} words marked as obsolete_or_archaic = TRUE")

        # Show breakdown
        print("\nBreakdown by evidence type:")
        cursor.execute("""
            SELECT
                COUNT(*) FILTER (WHERE definition ILIKE '%obsolete%') as obsolete,
                COUNT(*) FILTER (WHERE definition ILIKE '%archaic%') as archaic,
                COUNT(*) FILTER (WHERE definition ~ '\\[Obs\\.?\\]') as obs_brackets,
                COUNT(*) FILTER (WHERE definition ILIKE '%no longer%') as no_longer,
                COUNT(*) FILTER (WHERE definition ILIKE '%antiquated%') as antiquated
            FROM vocab.defined
            WHERE obsolete_or_archaic = TRUE
        """)

        result = cursor.fetchone()
        print(f"  'obsolete' marker:     {result[0]:,}")
        print(f"  'archaic' marker:      {result[1]:,}")
        print(f"  [Obs.] marker:         {result[2]:,}")
        print(f"  'no longer' marker:    {result[3]:,}")
        print(f"  'antiquated' marker:   {result[4]:,}")

        if not high_confidence_only:
            cursor.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE definition ILIKE '%dated%') as dated,
                    COUNT(*) FILTER (WHERE definition ILIKE '%formerly%') as formerly
                FROM vocab.defined
                WHERE obsolete_or_archaic = TRUE
                  AND NOT (
                      definition ILIKE '%obsolete%'
                      OR definition ILIKE '%archaic%'
                      OR definition ~ '\\[Obs\\.?\\]'
                      OR definition ILIKE '%no longer%'
                      OR definition ILIKE '%antiquated%'
                  )
            """)
            result = cursor.fetchone()
            print(f"\n  Medium confidence:")
            print(f"  'dated' marker:        {result[0]:,}")
            print(f"  'formerly' marker:     {result[1]:,}")

    cursor.close()
    conn.close()

    print("\n" + "=" * 80)
    if dry_run:
        print("DRY RUN COMPLETE - No changes made to database")
    else:
        print("COMPLETE - Database updated successfully")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description='Mark obsolete/archaic words in the database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/mark_obsolete_words.py                # Mark both high and medium confidence
  python scripts/mark_obsolete_words.py --high-only    # Mark only high confidence
  python scripts/mark_obsolete_words.py --dry-run      # Preview without updating
  python scripts/mark_obsolete_words.py --high-only --dry-run
        """
    )

    parser.add_argument(
        '--high-only',
        action='store_true',
        help='Only mark high confidence obsolete words (exclude medium confidence)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without updating the database'
    )

    args = parser.parse_args()

    try:
        mark_obsolete_words(
            high_confidence_only=args.high_only,
            dry_run=args.dry_run
        )
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
