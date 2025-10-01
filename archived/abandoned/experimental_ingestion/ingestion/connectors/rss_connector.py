#!/usr/bin/env python3
"""
RSS connector: fetch headlines and summaries from configured feeds.

Yields a sequence of dicts with keys: title, url, published_at, external_id.
Idempotent via external_id or hash.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional
import os
from config import VocabularyConfig


try:
    import feedparser  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    feedparser = None


DEFAULT_FEEDS: List[str] = [
    # Research/AI-focused sources (narrower scope)
    "https://www.nature.com/subjects/artificial-intelligence.rss",
    "https://www.nature.com/nature/articles?type=news-and-views.rss",
    "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml",
    "https://www.technologyreview.com/feed/",
]


def fetch_rss_documents(feeds: Optional[List[str]] = None, limit: Optional[int] = None) -> Iterable[Dict]:
    if feedparser is None:
        raise RuntimeError("feedparser is required for RSS connector. Install 'feedparser'.")

    # Allow override via environment variable RSS_FEEDS (comma-separated)
    if feeds is None:
        # Prefer config (with env fallback) when not explicitly passed
        feeds = VocabularyConfig.get_rss_feeds() or DEFAULT_FEEDS
    count = 0
    for url in feeds:
        try:
            d = feedparser.parse(url)
        except Exception:
            continue
        for e in d.entries:
            title = getattr(e, "title", None)
            link = getattr(e, "link", None)
            # Try to parse publication time
            published_at = None
            if getattr(e, "published_parsed", None):
                published_at = datetime(*e.published_parsed[:6])
            external_id = getattr(e, "id", None) or link
            yield {
                "title": title,
                "url": link,
                "published_at": published_at,
                "external_id": external_id,
                "source_name": url,
            }
            count += 1
            if limit and count >= limit:
                return
