#!/usr/bin/env python3
"""Filtering helpers for tokens/phrases.

Heuristics: exclude proper nouns/acronyms, numbers/URLs, function-word-only phrases.
"""

import re
from typing import List, Tuple, Optional
try:
    from wordfreq import zipf_frequency  # type: ignore
except Exception:  # pragma: no cover
    zipf_frequency = None


_url_re = re.compile(r"https?://|www\.")
_email_re = re.compile(r"\b[\w.]+@[\w.]+\.[a-z]{2,}\b", re.I)
_non_alpha_re = re.compile(r"^[^a-zA-Z]+$")
_acronym_re = re.compile(r"^[A-Z]{2,6}$")

_stopwords = set(
    """
    a an and are as at be by for from has have if in into is it its of on or that the to was were will with not but
    """.split()
)


def is_bad_token(token: str) -> bool:
    t = token.strip()
    if len(t) < 3:
        return True
    if _url_re.search(t) or _email_re.search(t):
        return True
    if _non_alpha_re.match(t):
        return True
    return False


def is_acronym(token: str) -> bool:
    return bool(_acronym_re.match(token))


def phrase_ok(tokens: List[str]) -> bool:
    # 2-3 tokens, at least one content word
    if not (2 <= len(tokens) <= 3):
        return False
    content = [t for t in tokens if t.lower() not in _stopwords]
    return len(content) >= 1


def normalize_token(token: str) -> str:
    return token.lower()


def is_common_word(token: str, threshold: float = 3.0) -> bool:
    """Return True if token is common by Zipf frequency (>= threshold).

    Threshold is hard-coded to 3.0 to target seriously rare terms.
    """
    if zipf_frequency is None:
        # Hard fail without wordfreq to avoid flooding with common words
        raise RuntimeError("wordfreq is required for rarity filtering. Install it: pip install wordfreq")
    try:
        z = zipf_frequency(token.lower(), "en")
        return z is not None and z >= threshold
    except Exception:
        return False
