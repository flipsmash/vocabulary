#!/usr/bin/env python3
"""
Comprehensive Rarity Maintenance Script

This script ensures complete and up-to-date rarity data by:
1. Backfilling missing frequency data (python_wordfreq, ngram_freq, commoncrawl_freq)
2. Refreshing the word_rarity_metrics materialized view
3. Updating final_rarity values in the defined table

Designed to be run via cron for regular maintenance.

Usage:
    # Full maintenance (default)
    python scripts/maintain_rarity.py

    # Dry run to see what would change
    python scripts/maintain_rarity.py --dry-run

    # Skip frequency updates (faster, only refreshes rarity)
    python scripts/maintain_rarity.py --skip-frequency

    # Skip view refresh (only update frequency data)
    python scripts/maintain_rarity.py --skip-refresh

    # Silent mode (only errors to stderr, good for cron)
    python scripts/maintain_rarity.py --silent

Example cron setup (daily at 2 AM):
    0 2 * * * cd /path/to/vocabulary && /path/to/.venv/bin/python scripts/maintain_rarity.py --silent >> /var/log/vocab_maintenance.log 2>&1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import psycopg
from core.config import VocabularyConfig

SENTINEL = -999.0
TEMP_DIR = PROJECT_ROOT / "temp"
COMMONCRAWL_LOOKUP = PROJECT_ROOT / "commoncrawl_data" / "fasttext_commoncrawl_lookup.txt.gz"


@dataclass
class MaintenanceStats:
    """Track maintenance operation statistics."""
    start_time: datetime
    end_time: datetime = None

    # Frequency data stats
    python_wordfreq_before: int = 0
    python_wordfreq_updated: int = 0
    python_wordfreq_failed: int = 0

    ngram_freq_before: int = 0
    ngram_freq_updated: int = 0
    ngram_freq_failed: int = 0

    commoncrawl_freq_before: int = 0
    commoncrawl_freq_updated: int = 0
    commoncrawl_freq_failed: int = 0

    # Rarity stats
    final_rarity_before: int = 0
    final_rarity_updated: int = 0

    view_refreshed: bool = False

    def duration_seconds(self) -> float:
        """Calculate duration in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Comprehensive rarity maintenance script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without committing updates"
    )
    parser.add_argument(
        "--skip-frequency",
        action="store_true",
        help="Skip frequency data updates (only refresh rarity)"
    )
    parser.add_argument(
        "--skip-refresh",
        action="store_true",
        help="Skip materialized view refresh (only update frequency data)"
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Silent mode - only output errors (good for cron)"
    )
    parser.add_argument(
        "--no-concurrently",
        dest="concurrently",
        action="store_false",
        help="Refresh view without CONCURRENTLY (locks the view)"
    )
    parser.set_defaults(concurrently=True)
    return parser.parse_args()


def get_db_connection() -> psycopg.Connection:
    """Get database connection with vocab schema."""
    return psycopg.connect(**VocabularyConfig.get_db_config())


def log(message: str, silent: bool = False, is_error: bool = False):
    """Log message to stdout/stderr based on flags."""
    if is_error:
        print(message, file=sys.stderr)
    elif not silent:
        print(message)


def count_missing_frequencies(conn: psycopg.Connection) -> tuple[int, int, int]:
    """Count words missing each frequency metric."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(CASE WHEN python_wordfreq IS NULL OR python_wordfreq = -999 THEN 1 END) as missing_python,
                COUNT(CASE WHEN ngram_freq IS NULL OR ngram_freq = -999 THEN 1 END) as missing_ngram,
                COUNT(CASE WHEN commoncrawl_freq IS NULL OR commoncrawl_freq = -999 THEN 1 END) as missing_commoncrawl
            FROM vocab.defined
            WHERE (phrase IS NULL OR phrase = 0) AND term NOT LIKE '% %'
        """)
        result = cur.fetchone()
        return result[0], result[1], result[2]


def count_missing_rarity(conn: psycopg.Connection) -> int:
    """Count words missing final_rarity."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM vocab.defined WHERE final_rarity IS NULL")
        return cur.fetchone()[0]


def normalize_term(term: str) -> str:
    """Normalize term for frequency lookup."""
    return term.strip().lower()


def fetch_all_frequency_candidates(conn: psycopg.Connection) -> List[Dict]:
    """Fetch ALL words that need any frequency data (not just those missing rarity)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, term, python_wordfreq, ngram_freq, commoncrawl_freq
            FROM vocab.defined
            WHERE (python_wordfreq IS NULL OR python_wordfreq = -999
                   OR ngram_freq IS NULL OR ngram_freq = -999
                   OR commoncrawl_freq IS NULL OR commoncrawl_freq = -999)
              AND (phrase IS NULL OR phrase = 0)
              AND term NOT LIKE '% %'
            ORDER BY id
        """)
        rows = cur.fetchall()

    candidates = []
    for word_id, term, py_freq, ng_freq, cc_freq in rows:
        if not term or not term.strip():
            continue
        candidates.append({
            "id": int(word_id),
            "term": term.strip(),
            "term_normalized": normalize_term(term),
            "python_wordfreq": py_freq,
            "ngram_freq": ng_freq,
            "commoncrawl_freq": cc_freq,
        })

    return candidates


def compute_python_wordfreq_scores(terms: List[str]) -> Dict[str, float]:
    """Compute python wordfreq scores."""
    if not terms:
        return {}

    try:
        from wordfreq import zipf_frequency
    except ImportError:
        log("Warning: wordfreq not available, skipping python_wordfreq updates", is_error=True)
        return {}

    scores = {}
    for term in terms:
        normalized = normalize_term(term)
        try:
            zipf = zipf_frequency(normalized, 'en')
            scores[normalized] = zipf if zipf > 0 else SENTINEL
        except:
            scores[normalized] = SENTINEL

    return scores


def compute_ngram_scores(terms: List[str]) -> Dict[str, float]:
    """Compute Google N-gram scores."""
    if not terms:
        return {}

    # Ensure temp directory exists
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    # Check for required files
    totals_path = TEMP_DIR / "googlebooks-eng-all-totalcounts-20120701.txt"
    if not totals_path.exists():
        log(f"Warning: N-gram totals file not found at {totals_path}", is_error=True)
        log("Run download/setup scripts to enable N-gram frequency updates", is_error=True)
        return {}

    try:
        sys.path.insert(0, str(TEMP_DIR))
        from getngrams import getNgrams
    except ImportError:
        log("Warning: getngrams module not available", is_error=True)
        return {}

    unique_terms = {normalize_term(t): t for t in terms}

    try:
        raw_scores = getNgrams(
            list(unique_terms.values()),
            corpus="eng_2019",
            startYear=1900,
            endYear=2019,
            smoothing=0,
            caseInsensitive=True,
            totalcounts_path=str(totals_path),
            year_start=1900,
            year_end=2019,
            aggregator="mean",
        )

        scores = {}
        for normalized in unique_terms:
            value = raw_scores.get(normalized)
            scores[normalized] = float(value) if value is not None else SENTINEL

        return scores
    except Exception as e:
        log(f"Warning: N-gram lookup failed: {e}", is_error=True)
        return {}


def compute_commoncrawl_scores(terms: List[str]) -> Dict[str, float]:
    """Compute Common Crawl scores."""
    if not terms:
        return {}

    if not COMMONCRAWL_LOOKUP.exists():
        log(f"Warning: Common Crawl lookup file not found at {COMMONCRAWL_LOOKUP}", is_error=True)
        log("Run download_commoncrawl_frequencies.py to enable Common Crawl updates", is_error=True)
        return {}

    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from commoncrawl_lookup import get_commoncrawl_frequency
    except ImportError:
        log("Warning: commoncrawl_lookup module not available", is_error=True)
        return {}

    unique_terms = {normalize_term(t): t for t in terms}

    scores = {}
    for normalized, original in unique_terms.items():
        try:
            value = get_commoncrawl_frequency(original, data_file=str(COMMONCRAWL_LOOKUP))
            scores[normalized] = float(value) if value and value > SENTINEL else SENTINEL
        except:
            scores[normalized] = SENTINEL

    return scores


def update_frequencies(
    conn: psycopg.Connection,
    candidates: List[Dict],
    silent: bool = False,
    dry_run: bool = False
) -> tuple[int, int, int, int, int, int]:
    """Update missing frequency data and return stats."""

    # Separate candidates by what they need
    python_terms = [c["term"] for c in candidates
                   if c["python_wordfreq"] is None or c["python_wordfreq"] == SENTINEL]
    ngram_terms = [c["term"] for c in candidates
                  if c["ngram_freq"] is None or c["ngram_freq"] == SENTINEL]
    commoncrawl_terms = [c["term"] for c in candidates
                        if c["commoncrawl_freq"] is None or c["commoncrawl_freq"] == SENTINEL]

    log(f"Computing frequencies for {len(python_terms)} python_wordfreq, {len(ngram_terms)} ngram, {len(commoncrawl_terms)} commoncrawl", silent)

    python_scores = compute_python_wordfreq_scores(python_terms)
    ngram_scores = compute_ngram_scores(ngram_terms)
    commoncrawl_scores = compute_commoncrawl_scores(commoncrawl_terms)

    # Build update lists
    python_updates = []
    ngram_updates = []
    commoncrawl_updates = []

    python_success = python_fail = 0
    ngram_success = ngram_fail = 0
    commoncrawl_success = commoncrawl_fail = 0

    for candidate in candidates:
        norm = candidate["term_normalized"]
        word_id = candidate["id"]

        if candidate["python_wordfreq"] is None or candidate["python_wordfreq"] == SENTINEL:
            value = python_scores.get(norm, SENTINEL)
            python_updates.append((value, word_id))
            if value != SENTINEL:
                python_success += 1
            else:
                python_fail += 1

        if candidate["ngram_freq"] is None or candidate["ngram_freq"] == SENTINEL:
            value = ngram_scores.get(norm, SENTINEL)
            ngram_updates.append((value, word_id))
            if value != SENTINEL:
                ngram_success += 1
            else:
                ngram_fail += 1

        if candidate["commoncrawl_freq"] is None or candidate["commoncrawl_freq"] == SENTINEL:
            value = commoncrawl_scores.get(norm, SENTINEL)
            commoncrawl_updates.append((value, word_id))
            if value != SENTINEL:
                commoncrawl_success += 1
            else:
                commoncrawl_fail += 1

    # Apply updates
    if not dry_run:
        with conn.cursor() as cur:
            if python_updates:
                cur.executemany(
                    "UPDATE vocab.defined SET python_wordfreq = %s WHERE id = %s",
                    python_updates
                )
            if ngram_updates:
                cur.executemany(
                    "UPDATE vocab.defined SET ngram_freq = %s WHERE id = %s",
                    ngram_updates
                )
            if commoncrawl_updates:
                cur.executemany(
                    "UPDATE vocab.defined SET commoncrawl_freq = %s WHERE id = %s",
                    commoncrawl_updates
                )
        conn.commit()

    return python_success, python_fail, ngram_success, ngram_fail, commoncrawl_success, commoncrawl_fail


def refresh_materialized_view(concurrently: bool = True, silent: bool = False):
    """Refresh the word_rarity_metrics materialized view."""
    refresh_sql = "REFRESH MATERIALIZED VIEW "
    if concurrently:
        refresh_sql += "CONCURRENTLY "
    refresh_sql += "word_rarity_metrics;"

    log(f"Refreshing materialized view (concurrently={concurrently})...", silent)

    with get_db_connection() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(refresh_sql)

    log("Materialized view refreshed", silent)


def update_final_rarity(conn: psycopg.Connection, dry_run: bool = False) -> int:
    """Update final_rarity from materialized view."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE vocab.defined AS d
            SET final_rarity = wrm.final_rarity
            FROM word_rarity_metrics AS wrm
            WHERE d.id = wrm.id
              AND d.final_rarity IS NULL
              AND wrm.final_rarity IS NOT NULL
        """)
        updated = cur.rowcount

        if not dry_run:
            conn.commit()

        return updated


def main():
    """Main maintenance routine."""
    args = parse_args()
    stats = MaintenanceStats(start_time=datetime.now())

    log("=" * 70, args.silent)
    log("VOCABULARY RARITY MAINTENANCE", args.silent)
    log("=" * 70, args.silent)
    log(f"Started: {stats.start_time.strftime('%Y-%m-%d %H:%M:%S')}", args.silent)
    if args.dry_run:
        log("DRY RUN MODE - No changes will be committed", args.silent)
    log("", args.silent)

    try:
        with get_db_connection() as conn:
            # Get initial stats
            py_missing, ng_missing, cc_missing = count_missing_frequencies(conn)
            rarity_missing = count_missing_rarity(conn)

            stats.python_wordfreq_before = py_missing
            stats.ngram_freq_before = ng_missing
            stats.commoncrawl_freq_before = cc_missing
            stats.final_rarity_before = rarity_missing

            log(f"Before maintenance:", args.silent)
            log(f"  python_wordfreq missing: {py_missing:,}", args.silent)
            log(f"  ngram_freq missing:      {ng_missing:,}", args.silent)
            log(f"  commoncrawl_freq missing: {cc_missing:,}", args.silent)
            log(f"  final_rarity missing:    {rarity_missing:,}", args.silent)
            log("", args.silent)

            # Update frequency data
            if not args.skip_frequency:
                log("Phase 1: Updating frequency data...", args.silent)
                candidates = fetch_all_frequency_candidates(conn)
                log(f"Found {len(candidates):,} words needing frequency updates", args.silent)

                if candidates:
                    (py_success, py_fail, ng_success, ng_fail,
                     cc_success, cc_fail) = update_frequencies(
                        conn, candidates, args.silent, args.dry_run
                    )

                    stats.python_wordfreq_updated = py_success
                    stats.python_wordfreq_failed = py_fail
                    stats.ngram_freq_updated = ng_success
                    stats.ngram_freq_failed = ng_fail
                    stats.commoncrawl_freq_updated = cc_success
                    stats.commoncrawl_freq_failed = cc_fail

                    log(f"  python_wordfreq: {py_success:,} updated, {py_fail:,} failed", args.silent)
                    log(f"  ngram_freq:      {ng_success:,} updated, {ng_fail:,} failed", args.silent)
                    log(f"  commoncrawl_freq: {cc_success:,} updated, {cc_fail:,} failed", args.silent)
                else:
                    log("  No frequency updates needed", args.silent)

                log("", args.silent)
            else:
                log("Phase 1: Skipped (--skip-frequency)", args.silent)
                log("", args.silent)

            # Refresh materialized view
            if not args.skip_refresh and not args.dry_run:
                log("Phase 2: Refreshing materialized view...", args.silent)
                refresh_materialized_view(args.concurrently, args.silent)
                stats.view_refreshed = True
                log("", args.silent)
            else:
                reason = "dry-run" if args.dry_run else "--skip-refresh"
                log(f"Phase 2: Skipped ({reason})", args.silent)
                log("", args.silent)

            # Update final_rarity
            if not args.dry_run:
                log("Phase 3: Updating final_rarity values...", args.silent)
                updated = update_final_rarity(conn, args.dry_run)
                stats.final_rarity_updated = updated
                log(f"  Updated {updated:,} final_rarity values", args.silent)
                log("", args.silent)
            else:
                log("Phase 3: Skipped (dry-run)", args.silent)
                log("", args.silent)

        stats.end_time = datetime.now()

        # Final summary
        log("=" * 70, args.silent)
        log("MAINTENANCE COMPLETE", args.silent)
        log("=" * 70, args.silent)
        log(f"Duration: {stats.duration_seconds():.1f} seconds", args.silent)

        if not args.skip_frequency:
            log(f"\nFrequency updates:", args.silent)
            log(f"  python_wordfreq: {stats.python_wordfreq_updated:,} updated", args.silent)
            log(f"  ngram_freq:      {stats.ngram_freq_updated:,} updated", args.silent)
            log(f"  commoncrawl_freq: {stats.commoncrawl_freq_updated:,} updated", args.silent)

        if stats.view_refreshed:
            log(f"\nMaterialized view: Refreshed", args.silent)

        if stats.final_rarity_updated > 0:
            log(f"\nRarity updates: {stats.final_rarity_updated:,} words", args.silent)

        log("", args.silent)
        sys.exit(0)

    except Exception as e:
        log(f"\nERROR: {e}", is_error=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
