#!/usr/bin/env python3
"""Definition fetching pipeline.

Primary sources: WordNet (if available), Wiktionary via pre-parsed dump (optional).
Fallback: usage-based gloss (placeholder).
"""

from __future__ import annotations

from typing import List, Optional, Tuple, Dict
import re

from ingestion.models import CandidateRepo
from ingestion.filters import is_common_word


def fetch_wordnet_definitions(lemma: str) -> List[Tuple[str, str, float]]:
    """Return list of (pos, gloss, confidence). Uses NLTK WordNet if available."""
    try:
        from nltk.corpus import wordnet as wn  # type: ignore

        out: List[Tuple[str, str, float]] = []
        for syn in wn.synsets(lemma):
            pos = syn.pos() or None
            gloss = syn.definition()
            if not gloss:
                continue
            conf = 0.6
            out.append((pos or "", gloss, conf))
        return out
    except Exception:
        return []


def upsert_definition_candidates(repo: CandidateRepo, candidate_id: int, lemma: str):
    """Insert a single definition per POS for the candidate.

    Strategy:
    - Determine candidate POS from candidate_terms.pos (coarse: NOUN/VERB/ADJ/ADV) if present.
    - If a definition already exists for (candidate_id, pos), do nothing.
    - Prefer a single WordNet sense matching that POS; else fallback usage-based gloss with that POS.
    - If candidate POS is NULL, pick a single best WordNet sense and use its POS; else fallback gloss with NULL POS.
    """
    # Safety guard: never create definitions for common terms
    if is_common_word(lemma):
        return

    conn = repo.get_conn()
    try:
        cur = conn.cursor()
        # Lookup candidate POS
        cur.execute("SELECT pos FROM candidate_terms WHERE id=%s", (candidate_id,))
        row = cur.fetchone()
        cand_pos: Optional[str] = row[0] if row else None
        # Check existing per (candidate_id, pos) with NULL-safe comparison
        cur.execute(
            """
            SELECT 1 FROM definition_candidates
            WHERE candidate_id=%s AND (
              (pos IS NULL AND %s IS NULL) OR pos = %s
            )
            LIMIT 1
            """,
            (candidate_id, cand_pos, cand_pos),
        )
        if cur.fetchone():
            cur.close()
            return

        # WordNet first (pick a single best sense)
        defs = fetch_wordnet_definitions(lemma)
        if defs:
            # Map wordnet POS to coarse POS tags
            pos_map = {"n": "NOUN", "v": "VERB", "a": "ADJ", "s": "ADJ", "r": "ADV"}
            # Filter by candidate POS if present
            if cand_pos:
                defs = [(p, g, c) for (p, g, c) in defs if pos_map.get(p or "", None) == cand_pos]
            if defs:
                # Choose a single sense by simple heuristic: shortest gloss
                p, gloss, conf = sorted(defs, key=lambda x: len(x[1]))[0]
                pos_tag = pos_map.get(p or "", None)
                cur.execute(
                    "INSERT INTO definition_candidates(candidate_id, source, pos, gloss, confidence) VALUES (%s,%s,%s,%s,%s)",
                    (candidate_id, "wordnet", pos_tag, gloss, conf),
                )
                conn.commit()
                cur.close()
                return

        # Fallback: usage-based gloss
        # Pull a few recent observations for this candidate
        cur.execute(
            """
            SELECT context_snippet FROM candidate_observations
            WHERE candidate_id=%s AND context_snippet IS NOT NULL
            ORDER BY observed_at DESC LIMIT 20
            """,
            (candidate_id,),
        )
        rows = [r[0] for r in cur.fetchall() if r and r[0]]
        if rows:
            gloss, example = _build_usage_gloss(rows, lemma)
            cur.execute(
                "INSERT INTO definition_candidates(candidate_id, source, pos, gloss, example, confidence) VALUES (%s,%s,%s,%s,%s,%s)",
                (candidate_id, "usage_gloss", cand_pos, gloss, example, 0.35),
            )
            conn.commit()
        cur.close()
    finally:
        conn.close()


_word_re = re.compile(r"[A-Za-z][A-Za-z\-']+")
_stop = set("a an and are as at be by for from has have if in into is it its of on or that the to was were will with not but this those these which who whom whose when where why how".split())


def _build_usage_gloss(snippets: List[str], lemma: str) -> Tuple[str, str]:
    # Naive keyword-based gloss from context snippets
    counts: Dict[str, int] = {}
    first_example = None
    for s in snippets:
        if not first_example and len(s) > 20:
            first_example = s[:200]
        for tok in _word_re.findall(s.lower()):
            if tok in _stop or tok == lemma:
                continue
            counts[tok] = counts.get(tok, 0) + 1
    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]
    keywords = ", ".join([w for w, c in top]) if top else "context-specific uses"
    gloss = f"A term used in contexts involving {keywords}."
    return gloss, (first_example or (snippets[0][:200] if snippets else ""))
