#!/usr/bin/env python3
"""
GitHub releases connector using repository Atom feeds.

Accepts a list of repo slugs (owner/repo). Yields release documents.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional
import os
from config import VocabularyConfig

try:
    import feedparser  # type: ignore
except Exception:  # pragma: no cover
    feedparser = None


DEFAULT_REPOS: List[str] = [
    # Focus on ML/NLP/ASR ecosystems
    "tensorflow/tensorflow",
    "pytorch/pytorch",
    "huggingface/transformers",
    "scikit-learn/scikit-learn",
    "openai/whisper",
]


def _releases_feed(repo: str) -> str:
    return f"https://github.com/{repo}/releases.atom"


def fetch_github_release_documents(repos: Optional[List[str]] = None, limit_per_repo: int = 50) -> Iterable[Dict]:
    if feedparser is None:
        raise RuntimeError("feedparser is required for GitHub connector. Install 'feedparser'.")
    # Allow override via environment variable GITHUB_REPOS (comma-separated owner/repo)
    if repos is None:
        repos = VocabularyConfig.get_github_repos() or DEFAULT_REPOS
    for r in repos:
        url = _releases_feed(r)
        try:
            d = feedparser.parse(url)
        except Exception:
            continue
        count = 0
        for e in d.entries:
            title = getattr(e, "title", None)
            link = getattr(e, "link", None)
            published_at = None
            if getattr(e, "published_parsed", None):
                published_at = datetime(*e.published_parsed[:6])
            external_id = getattr(e, "id", None) or link
            yield {
                "title": title,
                "url": link,
                "published_at": published_at,
                "external_id": external_id,
                "source_name": r,
            }
            count += 1
            if limit_per_repo and count >= limit_per_repo:
                break
