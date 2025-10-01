#!/usr/bin/env python3
"""Refresh the `final_rarity` column on the `defined` table.

This script converts the existing frequency metrics into rarity percentiles,
blends them with configurable weights, and stores the result back in Postgres.

Usage:
    source .venv/bin/activate && python analysis/update_final_rarity.py
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional
import sys

import pandas as pd
import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import VocabularyConfig


# Sentinel used throughout the project to indicate "data unavailable".
SENTINEL = -999

# Base weights for the rarity blend. The script re-normalises them depending on
# which metrics are available for each word.
RARITY_WEIGHTS: Dict[str, float] = {
    "python_wordfreq": 0.45,
    "ngram_freq": 0.35,
    "commoncrawl_freq": 0.20,
}

# Batch size for database updates.
UPDATE_BATCH_SIZE = 1000


@dataclass
class RefreshStats:
    total_rows: int
    updated_rows: int
    null_rows: int
    min_rarity: Optional[float]
    max_rarity: Optional[float]
    mean_rarity: Optional[float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recompute final rarity values.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute rarity values but do not write them back to the database.",
    )
    return parser.parse_args()


def get_connection() -> psycopg.Connection:
    return psycopg.connect(**VocabularyConfig.get_db_config())


def ensure_final_rarity_column(conn: psycopg.Connection) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE defined ADD COLUMN IF NOT EXISTS final_rarity NUMERIC(8,6)"
        )
    conn.commit()


def fetch_frequency_frame(conn: psycopg.Connection) -> pd.DataFrame:
    query = (
        "SELECT id, python_wordfreq, ngram_freq, commoncrawl_freq \n"
        "FROM defined"
    )
    df = pd.read_sql(query, conn)
    df.set_index("id", inplace=True)
    df.replace(SENTINEL, pd.NA, inplace=True)
    return df


def compute_rarity(df: pd.DataFrame) -> pd.Series:
    rarity_cols = []
    temp_columns: List[str] = []

    for column in RARITY_WEIGHTS:
        rarity_col = f"{column}_rarity"
        temp_columns.append(rarity_col)
        mask = df[column].notna()
        if mask.any():
            percentiles = df.loc[mask, column].rank(method="average", pct=True)
            df.loc[mask, rarity_col] = 1.0 - percentiles
        else:
            df[rarity_col] = pd.NA
        rarity_cols.append(rarity_col)

    def blend_row(row: pd.Series) -> Optional[float]:
        weighted_sum = 0.0
        total_weight = 0.0
        for column, weight in RARITY_WEIGHTS.items():
            rarity_value = row.get(f"{column}_rarity")
            if pd.isna(rarity_value):
                continue
            weighted_sum += float(rarity_value) * weight
            total_weight += weight
        if total_weight == 0:
            return pd.NA
        return weighted_sum / total_weight

    final_rarity = df.apply(blend_row, axis=1)
    df.drop(columns=temp_columns, inplace=True)
    return final_rarity


def chunked(iterable: Iterable, size: int) -> Iterable[List]:
    chunk: List = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def update_database(
    conn: psycopg.Connection,
    final_rarity: pd.Series,
    dry_run: bool,
) -> RefreshStats:
    cursor = conn.cursor()
    try:
        updates = []
        null_rows = 0
        for word_id, value in final_rarity.items():
            if pd.isna(value):
                updates.append((None, int(word_id)))
                null_rows += 1
            else:
                updates.append((round(float(value), 6), int(word_id)))

        if not dry_run:
            for chunk in chunked(updates, UPDATE_BATCH_SIZE):
                cursor.executemany(
                    "UPDATE defined SET final_rarity = %s WHERE id = %s",
                    chunk,
                )
            conn.commit()

        populated = [float(v) for v in final_rarity.dropna().tolist()]
        stats = RefreshStats(
            total_rows=len(final_rarity),
            updated_rows=len(updates),
            null_rows=null_rows,
            min_rarity=min(populated) if populated else None,
            max_rarity=max(populated) if populated else None,
            mean_rarity=sum(populated) / len(populated) if populated else None,
        )
        return stats
    finally:
        cursor.close()


def main() -> None:
    args = parse_args()

    conn = get_connection()
    try:
        ensure_final_rarity_column(conn)
        df = fetch_frequency_frame(conn)
    finally:
        conn.close()

    final_rarity = compute_rarity(df)

    conn = get_connection()
    try:
        stats = update_database(conn, final_rarity, args.dry_run)
    finally:
        conn.close()

    print("\nRefresh complete.")
    print(f"  Rows processed: {stats.total_rows:,}")
    print(f"  Rows updated:  {stats.updated_rows:,}")
    print(f"  Null rarity:   {stats.null_rows:,}")
    if stats.min_rarity is not None:
        print(
            "  Rarity range: {:.4f} – {:.4f} (mean {:.4f})".format(
                stats.min_rarity, stats.max_rarity, stats.mean_rarity
            )
        )
    if args.dry_run:
        print("\nDry-run: no database changes were committed.")


if __name__ == "__main__":
    main()
