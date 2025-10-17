#!/usr/bin/env python3
"""Generate exploratory plots for defined table frequency measures.

This script pulls `python_wordfreq`, `ngram_freq`, and `commoncrawl_freq` from
the `defined` table, treats `-999` as missing, and produces a multi-panel chart
to compare their distributions and pairwise relationships.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Provide Matplotlib a writable configuration directory when HOME is read-only.
os.environ.setdefault("MPLCONFIGDIR", str((PROJECT_ROOT / "analysis" / "mpl_cache").resolve()))

import matplotlib.pyplot as plt
import pandas as pd
import psycopg

from core.config import VocabularyConfig


OUTPUT_PATH = Path("analysis/frequency_measures.png")


def fetch_frequency_data() -> pd.DataFrame:
    """Load frequency metrics from the database as a DataFrame."""

    conn = psycopg.connect(**VocabularyConfig.get_db_config())
    try:
        query = (
            "SELECT python_wordfreq, ngram_freq, commoncrawl_freq "
            "FROM vocab.defined"
        )
        df = pd.read_sql(query, conn)
    finally:
        conn.close()

    # Replace sentinel values with NaN for easier plotting/statistics.
    df.replace(-999, pd.NA, inplace=True)

    return df


def make_plots(df: pd.DataFrame) -> None:
    """Render histograms and pairwise density plots for the frequency fields."""

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle(
        "Frequency Measure Comparison (python_wordfreq, ngram_freq, commoncrawl_freq)",
        fontsize=16,
    )

    freq_columns = [
        ("python_wordfreq", "Python WordFreq (Zipf)"),
        ("ngram_freq", "Google Ngram"),
        ("commoncrawl_freq", "Common Crawl FastText"),
    ]

    colors = ["#1b9e77", "#d95f02", "#7570b3"]

    # Row 1: histograms to show marginal distributions.
    for ax, (column, label), color in zip(axes[0], freq_columns, colors, strict=True):
        series = df[column].dropna().astype(float)
        ax.hist(series, bins=60, color=color, edgecolor="black", alpha=0.8)
        ax.set_title(f"Distribution: {label}")
        ax.set_xlabel("Frequency Value")
        ax.set_ylabel("Count")
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.4)

    # Row 2: pairwise density plots with Pearson correlations.
    comparisons = [
        ("python_wordfreq", "ngram_freq"),
        ("python_wordfreq", "commoncrawl_freq"),
        ("ngram_freq", "commoncrawl_freq"),
    ]

    for ax, (x_col, y_col) in zip(axes[1], comparisons, strict=True):
        subset = df[[x_col, y_col]].dropna().astype(float)
        if subset.empty:
            ax.text(0.5, 0.5, "No overlapping data", ha="center", va="center")
            ax.set_axis_off()
            continue

        hb = ax.hexbin(
            subset[x_col],
            subset[y_col],
            gridsize=50,
            cmap="viridis",
            mincnt=1,
        )
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.set_title(f"{x_col} vs {y_col}")
        cb = fig.colorbar(hb, ax=ax)
        cb.set_label("Count")
        correlation = subset[x_col].corr(subset[y_col])
        ax.text(
            0.02,
            0.98,
            f"Pearson r = {correlation:.2f}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            bbox=dict(facecolor="white", alpha=0.7, edgecolor="none"),
        )
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.4)

    plt.tight_layout(rect=(0, 0, 1, 0.97))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUTPUT_PATH, dpi=200)
    plt.close(fig)


def main() -> None:
    df = fetch_frequency_data()
    make_plots(df)
    print(f"Visualization saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
