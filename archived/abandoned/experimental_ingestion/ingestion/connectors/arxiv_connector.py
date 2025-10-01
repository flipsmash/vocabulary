#!/usr/bin/env python3
"""
arXiv connector using Atom API via feedparser.

Yields documents with title, url, published_at, external_id.
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


DEFAULT_CATEGORIES = [
    # Narrowed to AI/ML/ASR/CL
    "cs.CL",
    "cs.LG",
    "cs.AI",
    "stat.ML",
    "eess.AS",
]


def _build_search_query(categories: List[str]) -> str:
    parts = [f"cat:{c}" for c in categories]
    return "+OR+".join(parts)


def fetch_arxiv_documents(categories: Optional[List[str]] = None, max_results: int = 200) -> Iterable[Dict]:
    if feedparser is None:
        raise RuntimeError("feedparser is required for arXiv connector. Install 'feedparser'.")

    # Allow override via environment variable ARXIV_CATEGORIES (comma-separated)
    if categories is None:
        cats = VocabularyConfig.get_arxiv_categories() or DEFAULT_CATEGORIES
    else:
        cats = categories
    query = _build_search_query(cats)
    base = "http://export.arxiv.org/api/query"
    url = f"{base}?search_query={query}&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    d = feedparser.parse(url)
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
            "source_name": "arxiv",
        }
