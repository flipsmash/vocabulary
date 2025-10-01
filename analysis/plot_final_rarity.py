#!/usr/bin/env python3
"""Visualize the blended final_rarity metric and its relationship to inputs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psycopg


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("MPLCONFIGDIR", str((PROJECT_ROOT / "analysis" / "mpl_cache").resolve()))

from core.config import VocabularyConfig


OUTPUT_PATH = Path("analysis/final_rarity.png")
SENTINEL = -999


def fetch_data() -> pd.DataFrame:
    conn = psycopg.connect(**VocabularyConfig.get_db_config())
    try:
        query = (
            "SELECT id, final_rarity, python_wordfreq, ngram_freq, commoncrawl_freq "
            "FROM defined"
        )
        df = pd.read_sql(query, conn)
    finally:
        conn.close()

    df.set_index("id", inplace=True)
    df.replace(SENTINEL, pd.NA, inplace=True)
    return df


def make_plots(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle("Final Rarity Overview", fontsize=16)

    rarity = df["final_rarity"].dropna().astype(float)

    # Histogram of final_rarity
    axes[0, 0].hist(rarity, bins=50, color="#4daf4a", edgecolor="black", alpha=0.85)
    axes[0, 0].set_xlabel("final_rarity (0=common, 1=rare)")
    axes[0, 0].set_ylabel("Count")
    axes[0, 0].set_title("Distribution")
    axes[0, 0].grid(True, linestyle="--", linewidth=0.5, alpha=0.4)

    # Empirical CDF
    sorted_vals = np.sort(rarity.values)
    ecdf = np.arange(1, len(sorted_vals) + 1) / len(sorted_vals)
    axes[0, 1].plot(sorted_vals, ecdf, color="#377eb8", linewidth=2)
    axes[0, 1].set_xlabel("final_rarity")
    axes[0, 1].set_ylabel("Cumulative proportion")
    axes[0, 1].set_title("Empirical CDF")
    axes[0, 1].grid(True, linestyle="--", linewidth=0.5, alpha=0.4)

    # Coverage counts (number of contributing metrics)
    coverage_counts = (
        df[["python_wordfreq", "ngram_freq", "commoncrawl_freq"]]
        .notna()
        .sum(axis=1)
    )
    bars = coverage_counts.value_counts().sort_index()
    axes[0, 2].bar(bars.index.astype(int), bars.values, color="#ff7f00", edgecolor="black")
    axes[0, 2].set_xlabel("Number of available metrics")
    axes[0, 2].set_ylabel("Word count")
    axes[0, 2].set_title("Coverage contributing to final_rarity")
    axes[0, 2].set_xticks([0, 1, 2, 3])
    axes[0, 2].grid(True, axis="y", linestyle="--", linewidth=0.5, alpha=0.4)

    comparisons = [
        ("python_wordfreq", "Python WordFreq (Zipf)", "#1b9e77"),
        ("ngram_freq", "Google Ngram", "#d95f02"),
        ("commoncrawl_freq", "Common Crawl FastText", "#7570b3"),
    ]

    for ax, (column, label, color) in zip(axes[1], comparisons, strict=True):
        subset = df[["final_rarity", column]].dropna().astype(float)
        if subset.empty:
            ax.text(0.5, 0.5, "No overlapping data", ha="center", va="center")
            ax.set_axis_off()
            continue

        hb = ax.hexbin(
            subset[column],
            subset["final_rarity"],
            gridsize=50,
            cmap="viridis",
            mincnt=1,
        )
        ax.set_xlabel(label)
        ax.set_ylabel("final_rarity")
        ax.set_title(f"final_rarity vs {label}")
        cb = fig.colorbar(hb, ax=ax)
        cb.set_label("Count")
        correlation = subset[column].corr(subset["final_rarity"])
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

    axes[1, 2].set_ylabel("final_rarity")

    plt.tight_layout(rect=(0, 0, 1, 0.97))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUTPUT_PATH, dpi=200)
    plt.close(fig)


def main() -> None:
    df = fetch_data()
    make_plots(df)
    print(f"Visualization saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
