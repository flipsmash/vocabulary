#!/usr/bin/env python3
"""
Maintain pronunciation data for vocabulary words.

This script generates and updates pronunciation data (IPA, ARPAbet, syllables, stress)
for words in the database using a 3-tier system:
1. CMU Pronouncing Dictionary (primary, most accurate)
2. Online Dictionary API (fallback, requires internet)
3. Rule-based generation (last resort, requires --include-fallback flag)

Designed to be run via cron for regular maintenance.

Usage:
    # Update NULL pronunciations using CMU + API only
    python scripts/maintain_pronunciation.py

    # Include rule-based fallback for remaining words
    python scripts/maintain_pronunciation.py --include-fallback

    # Force re-check ALL words (not just NULLs)
    python scripts/maintain_pronunciation.py --force-recheck

    # Dry run to preview changes
    python scripts/maintain_pronunciation.py --dry-run

    # Silent mode (only errors to stderr, good for cron)
    python scripts/maintain_pronunciation.py --silent

Example cron setup (daily at 2 AM):
    0 2 * * * cd /path/to/vocabulary && /path/to/.venv/bin/python scripts/maintain_pronunciation.py --silent >> /var/log/vocab_maintenance.log 2>&1
"""

import argparse
import sys
import json
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import psycopg
from core.secure_config import get_database_config
from pronunciation.modern_pronunciation_system import ModernPhoneticProcessor


# Sentinel value for "checked but not found"
NOT_FOUND_MARKER = "NOT_FOUND"


def maintain_pronunciations(
    dry_run: bool = False,
    silent: bool = False,
    force_recheck: bool = False,
    include_fallback: bool = False
):
    """
    Find and generate pronunciation data for words missing it.

    Args:
        dry_run: If True, preview changes without updating database
        silent: If True, suppress informational output
        force_recheck: If True, recheck ALL words regardless of current value
        include_fallback: If True, use rule-based fallback (Tier 3) for remaining words
    """
    def log(message: str, is_error: bool = False):
        """Log message unless in silent mode."""
        if not silent or is_error:
            stream = sys.stderr if is_error else sys.stdout
            print(message, file=stream, flush=True)

    start_time = datetime.now()
    log(f"Starting pronunciation maintenance at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

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

    # Check if table exists
    log("\n1. Checking word_phonetics table...")
    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_name = 'word_phonetics'
    """, (config.schema,))

    table_exists = cursor.fetchone()
    if not table_exists:
        log("   Creating word_phonetics table...")
        if not dry_run:
            cursor.execute("""
                CREATE TABLE vocab.word_phonetics (
                    word_id INTEGER PRIMARY KEY,
                    word VARCHAR(255) NOT NULL,
                    ipa_transcription TEXT,
                    arpabet_transcription TEXT,
                    syllable_count INTEGER,
                    stress_pattern VARCHAR(50),
                    phonemes_json TEXT,
                    transcription_source VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (word_id) REFERENCES defined(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE INDEX idx_word_phonetics_source
                ON vocab.word_phonetics (transcription_source)
            """)
            conn.commit()
        log("   ✓ Table created")
    else:
        log("   ✓ Table exists")

    # Count words needing pronunciation
    if force_recheck:
        log("\n2. Force recheck enabled - processing ALL words...")
        cursor.execute("""
            SELECT COUNT(*)
            FROM vocab.defined
        """)
        word_count = cursor.fetchone()[0]
        log(f"   Found {word_count:,} total words to check")
    else:
        log("\n2. Finding words without pronunciation data...")
        cursor.execute("""
            SELECT COUNT(*)
            FROM vocab.defined d
            LEFT JOIN vocab.word_phonetics wp ON d.id = wp.word_id
            WHERE wp.word_id IS NULL OR wp.ipa_transcription IS NULL
        """)
        word_count = cursor.fetchone()[0]
        log(f"   Found {word_count:,} words without pronunciation data")

    if word_count == 0 and not force_recheck:
        log("\n✓ All words have pronunciation data")
        cursor.close()
        conn.close()
        return

    # Get words to process
    log(f"\n3. Fetching words...")
    if force_recheck:
        cursor.execute("""
            SELECT d.id, d.term
            FROM vocab.defined d
            ORDER BY d.id
        """)
    else:
        cursor.execute("""
            SELECT d.id, d.term
            FROM vocab.defined d
            LEFT JOIN vocab.word_phonetics wp ON d.id = wp.word_id
            WHERE wp.word_id IS NULL OR wp.ipa_transcription IS NULL
            ORDER BY d.id
        """)

    words_to_process = cursor.fetchall()
    log(f"   Retrieved {len(words_to_process):,} words")

    if len(words_to_process) == 0:
        log("\n✓ No words need processing")
        cursor.close()
        conn.close()
        return

    # Initialize pronunciation processor
    log(f"\n4. Initializing pronunciation processor...")
    log(f"   Loading CMU Dictionary and models...")
    processor = ModernPhoneticProcessor()
    log(f"   ✓ Processor ready")

    # Process each word
    log(f"\n5. Processing pronunciations...")
    log(f"   Include fallback rules: {'YES' if include_fallback else 'NO (Tier 1-2 only)'}")
    log(f"   Dry run: {'YES (no changes will be made)' if dry_run else 'NO (will update database)'}")

    cmu_count = 0
    api_count = 0
    fallback_count = 0
    not_found_count = 0
    error_count = 0

    pronunciations_to_insert = []
    pronunciations_to_update = []

    for i, (word_id, term) in enumerate(words_to_process, 1):
        if not silent and i % 100 == 0:
            log(f"   Progress: {i:,}/{len(words_to_process):,} words...")

        try:
            # Get pronunciation data
            phonetic_data = processor.transcribe_word(term)

            # Check what source was used
            source = phonetic_data.source

            # Skip fallback results if not requested
            if source == "Fallback Rules" and not include_fallback:
                # Mark as checked but not found
                not_found_count += 1
                if not dry_run:
                    pronunciations_to_insert.append((
                        word_id,
                        term,
                        NOT_FOUND_MARKER,
                        NOT_FOUND_MARKER,
                        None,
                        None,
                        None,
                        "Not Found (CMU/API)"
                    ))
                continue

            # Skip error results
            if source == "Error":
                error_count += 1
                continue

            # Count by source
            if source == "CMU Dictionary":
                cmu_count += 1
            elif source == "Online API":
                api_count += 1
            elif source == "Fallback Rules":
                fallback_count += 1

            # Prepare data for database
            phonemes_json = json.dumps(phonetic_data.phonemes) if phonetic_data.phonemes else None

            if not dry_run:
                # Check if word already exists in word_phonetics
                cursor.execute("""
                    SELECT word_id FROM vocab.word_phonetics WHERE word_id = %s
                """, (word_id,))
                exists = cursor.fetchone()

                if exists:
                    pronunciations_to_update.append((
                        phonetic_data.ipa,
                        phonetic_data.arpabet,
                        phonetic_data.syllable_count,
                        phonetic_data.stress_pattern,
                        phonemes_json,
                        source,
                        word_id
                    ))
                else:
                    pronunciations_to_insert.append((
                        word_id,
                        term,
                        phonetic_data.ipa,
                        phonetic_data.arpabet,
                        phonetic_data.syllable_count,
                        phonetic_data.stress_pattern,
                        phonemes_json,
                        source
                    ))

        except Exception as e:
            error_count += 1
            if not silent:
                log(f"   Error processing '{term}': {e}", is_error=True)

    log(f"\n   Processing complete:")
    log(f"   - CMU Dictionary (Tier 1): {cmu_count:,}")
    log(f"   - Online API (Tier 2): {api_count:,}")
    if include_fallback:
        log(f"   - Fallback Rules (Tier 3): {fallback_count:,}")
    log(f"   - Not found (marked): {not_found_count:,}")
    log(f"   - Errors (skipped): {error_count:,}")

    if dry_run:
        log(f"\n[DRY RUN] Would insert {len(pronunciations_to_insert):,} new pronunciations")
        log(f"[DRY RUN] Would update {len(pronunciations_to_update):,} existing pronunciations")

        # Show sample results
        if pronunciations_to_insert:
            log(f"\n   Sample words that would be added:")
            for data in pronunciations_to_insert[:5]:
                word_id, term, ipa, arpabet, syllables, stress, _, source = data
                if ipa == NOT_FOUND_MARKER:
                    log(f"   - {term} (ID: {word_id}): {source}")
                else:
                    log(f"   - {term} (ID: {word_id}): IPA={ipa}, syllables={syllables}, source={source}")
    else:
        # Update database
        log(f"\n6. Updating database...")

        # Insert new pronunciations
        if pronunciations_to_insert:
            cursor.executemany("""
                INSERT INTO vocab.word_phonetics
                (word_id, word, ipa_transcription, arpabet_transcription,
                 syllable_count, stress_pattern, phonemes_json, transcription_source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, pronunciations_to_insert)
            log(f"   ✓ Inserted {len(pronunciations_to_insert):,} new pronunciation records")

        # Update existing pronunciations
        if pronunciations_to_update:
            cursor.executemany("""
                UPDATE vocab.word_phonetics
                SET ipa_transcription = %s,
                    arpabet_transcription = %s,
                    syllable_count = %s,
                    stress_pattern = %s,
                    phonemes_json = %s,
                    transcription_source = %s
                WHERE word_id = %s
            """, pronunciations_to_update)
            log(f"   ✓ Updated {len(pronunciations_to_update):,} existing pronunciation records")

        conn.commit()

        # Verify the update
        cursor.execute("""
            SELECT COUNT(*)
            FROM vocab.word_phonetics
            WHERE ipa_transcription IS NULL OR ipa_transcription = %s
        """, (NOT_FOUND_MARKER,))
        remaining_nulls = cursor.fetchone()[0]
        log(f"   ✓ Verification: {remaining_nulls:,} words still without pronunciation")

    # Final statistics
    log(f"\n7. Summary statistics:")
    cursor.execute("""
        SELECT
            COUNT(*) FILTER (WHERE transcription_source = 'CMU Dictionary') as cmu_count,
            COUNT(*) FILTER (WHERE transcription_source = 'Online API') as api_count,
            COUNT(*) FILTER (WHERE transcription_source = 'Fallback Rules') as fallback_count,
            COUNT(*) FILTER (WHERE transcription_source LIKE 'Not Found%') as not_found_count,
            COUNT(*) FILTER (WHERE ipa_transcription IS NULL) as null_count,
            COUNT(*) as total_count
        FROM vocab.word_phonetics
    """)
    stats = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) FROM vocab.defined")
    total_words = cursor.fetchone()[0]

    log(f"   - CMU Dictionary (Tier 1):  {stats[0]:,}")
    log(f"   - Online API (Tier 2):      {stats[1]:,}")
    log(f"   - Fallback Rules (Tier 3):  {stats[2]:,}")
    log(f"   - Not found (marked):       {stats[3]:,}")
    log(f"   - NULL (not yet checked):   {stats[4]:,}")
    log(f"   - Total pronunciations:     {stats[5]:,}")
    log(f"   - Total words in database:  {total_words:,}")
    log(f"   - Coverage: {100.0 * stats[5] / total_words:.2f}%")

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
        description='Maintain pronunciation data for vocabulary words',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/maintain_pronunciation.py                    # Update NULLs with CMU+API
  python scripts/maintain_pronunciation.py --include-fallback # Include rule-based fallback
  python scripts/maintain_pronunciation.py --dry-run          # Preview without updating
  python scripts/maintain_pronunciation.py --silent           # Silent mode for cron
  python scripts/maintain_pronunciation.py --force-recheck    # Recheck ALL words
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

    parser.add_argument(
        '--include-fallback',
        action='store_true',
        help='Include rule-based fallback (Tier 3) for words not found in CMU/API'
    )

    args = parser.parse_args()

    try:
        maintain_pronunciations(
            dry_run=args.dry_run,
            silent=args.silent,
            force_recheck=args.force_recheck,
            include_fallback=args.include_fallback
        )
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
