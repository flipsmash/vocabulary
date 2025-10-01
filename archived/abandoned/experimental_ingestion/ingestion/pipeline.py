#!/usr/bin/env python3
"""Ingestion pipeline orchestration.

Implements a minimal end-to-end flow for RSS: fetch docs, tokenize,
filter candidates, persist observations, compute basic scores, and fetch
definitions when possible.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Tuple
from datetime import datetime

from ingestion.models import CandidateRepo
from ingestion.connectors.rss_connector import fetch_rss_documents
from ingestion.connectors.arxiv_connector import fetch_arxiv_documents
from ingestion.connectors.github_releases_connector import fetch_github_release_documents
from ingestion.filters import is_bad_token, is_acronym, phrase_ok, normalize_token, is_common_word
from ingestion.scoring import compute_metrics
from ingestion import filters as filters_mod
from ingestion import definitions as defs_mod


_word_re = re.compile(r"[A-Za-z][A-Za-z\-']+")

try:
    import spacy  # type: ignore
    _SPACY_AVAILABLE = True
except Exception:  # pragma: no cover
    spacy = None
    _SPACY_AVAILABLE = False

_NLP = None


def _get_nlp():
    global _NLP
    if _NLP is not None:
        return _NLP
    if not _SPACY_AVAILABLE:
        raise RuntimeError("spaCy is required for robust proper-noun exclusion. Please install spacy and the en_core_web_sm model.")
    try:
        # Enable NER to better filter named entities (proper nouns and orgs)
        _NLP = spacy.load("en_core_web_sm")
        return _NLP
    except Exception:
        raise RuntimeError("spaCy model 'en_core_web_sm' not installed. Run: python -m spacy download en_core_web_sm")


def _simple_tokenize(text: str) -> List[str]:
    return _word_re.findall(text or "")


def _extract_phrases(tokens: List[str]) -> List[List[str]]:
    phrases: List[List[str]] = []
    for n in (2, 3):
        for i in range(0, len(tokens) - n + 1):
            span = tokens[i : i + n]
            if phrase_ok(span):
                phrases.append(span)
    return phrases


def _tag_tokens(text: str) -> List[Tuple[str, str, Optional[str], Optional[str], Optional[str]]]:
    """Return list of (display, lemma_lower, pos) tokens.

    Uses spaCy if available; otherwise falls back to regex tokenization.
    """
    nlp = _get_nlp()
    out: List[Tuple[str, str, Optional[str], Optional[str], Optional[str]]] = []
    if nlp:
        doc = nlp(text or "")
        for t in doc:
            if not (t.is_alpha or "-" in t.text or "'" in t.text):
                continue
            disp = t.text
            lemma = (t.lemma_ or disp).lower()
            pos = t.pos_ if t.pos_ else None
            tag = t.tag_ if t.tag_ else None
            ent = t.ent_type_ if t.ent_type_ else None
            out.append((disp, lemma, pos, tag, ent))
        return out
    # Fallback
    toks = _simple_tokenize(text)
    return [(t, t.lower(), None, None, None) for t in toks]


def run_rss_ingestion(limit: Optional[int] = 200) -> int:
    """Run RSS ingestion end-to-end. Returns number of candidates touched."""
    repo = CandidateRepo()
    repo.create_tables_if_not_exists()

    source_id = repo.upsert_source(name="rss", type_="rss", url="multiple")
    touched = 0

    for doc in fetch_rss_documents(limit=limit):
        # Persist document
        doc_id = repo.upsert_document(
            source_id=source_id,
            title=doc.get("title"),
            url=doc.get("url"),
            published_at=doc.get("published_at"),
            external_id=doc.get("external_id"),
            lang="en",
        )

        text = (doc.get("title") or "")
        tagged = _tag_tokens(text)
        # Filters: bad token, acronym, common words, proper nouns and entities
        filtered = []
        for disp, lemma, pos, tag, ent in tagged:
            if is_bad_token(disp) or is_acronym(disp) or is_common_word(lemma):
                continue
            if pos == "PROPN" or (tag in ("NNP", "NNPS")):
                continue
            if ent:  # has named entity type like ORG, PERSON, GPE
                continue
            filtered.append((disp, lemma, pos))

        # Single tokens
        for disp, lemma, pos in filtered:
            ngram_len = 1
            cand_id, created = repo.upsert_candidate(
                lemma=lemma,
                display=disp,
                ngram_len=ngram_len,
                pos=pos,
                origin="rss",
                primary_source_id=source_id,
            )
            repo.add_observation(
                candidate_id=cand_id,
                document_id=doc_id,
                token_or_phrase=disp,
                start_idx=None,
                context_snippet=text[:200],
            )
            metrics = compute_metrics(lemma=lemma, display=disp, ngram_len=ngram_len)
            repo.upsert_metrics(cand_id, metrics)
            if created:
                defs_mod.upsert_definition_candidates(repo, cand_id, lemma)
            touched += 1

        # Phrases
        # Phrases disabled by request (skip)

    return touched


def _ingest_documents(docs: Iterable[dict], origin: str, source_label: str, repo: CandidateRepo) -> int:
    source_id = repo.upsert_source(name=source_label, type_=origin, url="multiple")
    touched = 0
    for doc in docs:
        doc_id = repo.upsert_document(
            source_id=source_id,
            title=doc.get("title"),
            url=doc.get("url"),
            published_at=doc.get("published_at"),
            external_id=doc.get("external_id"),
            lang="en",
        )
        text = (doc.get("title") or "")
        tagged = _tag_tokens(text)
        filtered = []
        for disp, lemma, pos, tag, ent in tagged:
            if is_bad_token(disp) or is_acronym(disp) or is_common_word(lemma):
                continue
            if pos == "PROPN" or (tag in ("NNP", "NNPS")):
                continue
            if ent:
                continue
            filtered.append((disp, lemma, pos))

        for disp, lemma, pos in filtered:
            cand_id, created = repo.upsert_candidate(
                lemma=lemma,
                display=disp,
                ngram_len=1,
                pos=pos,
                origin=origin,
                primary_source_id=source_id,
            )
            repo.add_observation(cand_id, doc_id, disp, None, text[:200])
            metrics = compute_metrics(lemma=lemma, display=disp, ngram_len=1)
            repo.upsert_metrics(cand_id, metrics)
            if created:
                defs_mod.upsert_definition_candidates(repo, cand_id, lemma)
            touched += 1

        # Phrases disabled by request (skip)
    return touched


def run_arxiv_ingestion(limit: Optional[int] = 200, categories: Optional[list] = None) -> int:
    repo = CandidateRepo()
    repo.create_tables_if_not_exists()
    docs = fetch_arxiv_documents(categories=categories, max_results=limit or 200)
    return _ingest_documents(docs, origin="arxiv", source_label="arxiv", repo=repo)


def run_github_ingestion(limit_per_repo: int = 50, repos: Optional[list] = None) -> int:
    repo = CandidateRepo()
    repo.create_tables_if_not_exists()
    docs = fetch_github_release_documents(repos=repos, limit_per_repo=limit_per_repo)
    return _ingest_documents(docs, origin="github", source_label="github_releases", repo=repo)
