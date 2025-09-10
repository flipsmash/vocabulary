#!/usr/bin/env python3
"""Scoring and metrics computation for candidate terms.

Lightweight implementation with optional wordfreq support.
"""

from __future__ import annotations

from typing import Dict, Optional


def _zipf_frequency(word: str) -> Optional[float]:
    try:
        from wordfreq import zipf_frequency  # type: ignore

        return zipf_frequency(word, "en")
    except Exception:
        return None


def compute_metrics(lemma: str, display: str, ngram_len: int) -> Dict[str, float]:
    # Very simple metrics with sensible defaults
    zipf = _zipf_frequency(lemma) if ngram_len == 1 else None
    if zipf is None:
        rarity_z = 1.0  # assume rare
    else:
        # Zipf ~ 1-7 (rare-high); convert to rarity z-like score
        rarity_z = max(0.0, 6.0 - zipf)

    # No burst, novelty, diversity without history yet; default to 0
    burstiness = 0.0
    source_diversity = 0.0
    context_diversity = 0.0
    novelty = 0.5  # assume somewhat novel until proven
    length_complexity = min(1.0, max(0.0, (len(display) - 6) / 10.0))
    typo_risk = 0.0
    safety_penalty = 0.0

    score = (
        1.0 * rarity_z
        + 0.0 * burstiness
        + 0.2 * source_diversity
        + 0.2 * context_diversity
        + 0.6 * novelty
        + 0.1 * length_complexity
        - 0.3 * typo_risk
        - 0.0 * safety_penalty
    )

    return {
        "score": float(score),
        "rarity_z": float(rarity_z),
        "burstiness": float(burstiness),
        "source_diversity": float(source_diversity),
        "context_diversity": float(context_diversity),
        "novelty": float(novelty),
        "length_complexity": float(length_complexity),
        "typo_risk": float(typo_risk),
        "safety_penalty": float(safety_penalty),
    }

