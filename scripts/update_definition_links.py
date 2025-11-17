#!/usr/bin/env python3
"""
Precompute HTML-linked definitions by inserting anchors for in-vocabulary terms.

Usage examples:
    python scripts/update_definition_links.py
    python scripts/update_definition_links.py --dry-run --limit 500

The script scans vocab.defined, ensures the `definition_with_links` column exists,
and stores HTML snippets that the web app can display with `|safe`.
"""

from __future__ import annotations

import argparse
import html
import logging
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from core.database_manager import db_manager

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

WORD_PATTERN = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*")


def normalize_tokens(value: str) -> Tuple[str, ...]:
    """Split a term into lowercase word tokens (letters, apostrophes, hyphens)."""
    if not value:
        return tuple()
    return tuple(token.lower() for token in WORD_PATTERN.findall(value))


def tokenize_definition(value: str) -> List[Dict[str, str | bool]]:
    """Return a token stream preserving delimiters for reconstruction."""
    tokens: List[Dict[str, str | bool]] = []
    if not value:
        return tokens

    cursor = 0
    for match in WORD_PATTERN.finditer(value):
        start, end = match.span()
        if start > cursor:
            tokens.append({"text": value[cursor:start], "is_word": False})
        tokens.append(
            {
                "text": match.group(0),
                "is_word": True,
                "word_lower": match.group(0).lower(),
            }
        )
        cursor = end

    if cursor < len(value):
        tokens.append({"text": value[cursor:], "is_word": False})

    return tokens


@dataclass(frozen=True)
class VocabularyEntry:
    word_id: int
    tokens: Tuple[str, ...]


class DefinitionLinkBuilder:
    """Build and persist linked definitions."""

    def __init__(
        self,
        *,
        min_term_length: int = 3,
        max_links_per_definition: int = 25,
    ):
        self.min_term_length = max(1, min_term_length)
        self.max_links_per_definition = max(1, max_links_per_definition)
        self._first_word_map: Dict[str, List[VocabularyEntry]] = {}
        self._max_term_words: int = 1

    def ensure_column(self) -> None:
        """Ensure destination column exists."""
        with db_manager.get_cursor() as cursor:
            cursor.execute(
                """
                ALTER TABLE vocab.defined
                ADD COLUMN IF NOT EXISTS definition_with_links TEXT
                """
            )

    def load_vocabulary(self) -> None:
        """Build index of known vocabulary terms."""
        term_index: Dict[Tuple[str, ...], VocabularyEntry] = {}

        with db_manager.get_cursor() as cursor:
            cursor.execute("SELECT id, term FROM vocab.defined WHERE term IS NOT NULL")
            rows = cursor.fetchall()

        for word_id, term in rows:
            tokens = normalize_tokens(term)
            if not tokens:
                continue
            if all(len(token) < self.min_term_length for token in tokens):
                continue
            entry = term_index.get(tokens)
            if entry is None or word_id < entry.word_id:
                term_index[tokens] = VocabularyEntry(word_id=word_id, tokens=tokens)

        first_word_map: Dict[str, List[VocabularyEntry]] = {}
        for entry in term_index.values():
            first_word_map.setdefault(entry.tokens[0], []).append(entry)

        self._first_word_map = first_word_map
        self._max_term_words = max((len(entry.tokens) for entry in term_index.values()), default=1)
        logger.info(
            "Loaded %s vocabulary keys (%s max words, min token length %s)",
            f"{len(term_index):,}",
            self._max_term_words,
            self.min_term_length,
        )

    def build_html(self, definition: str) -> Tuple[Optional[str], int]:
        """Return HTML (if links inserted) and number of replacements."""
        if not definition:
            return None, 0

        tokens = tokenize_definition(definition)
        if not tokens:
            return None, 0

        word_token_indices = [idx for idx, token in enumerate(tokens) if token.get("is_word")]
        if not word_token_indices:
            return None, 0

        spans: Dict[int, Tuple[int, str]] = {}
        replacements = 0
        word_cursor = 0

        while word_cursor < len(word_token_indices):
            if replacements >= self.max_links_per_definition:
                break

            token_index = word_token_indices[word_cursor]
            token_lower = tokens[token_index]["word_lower"]  # type: ignore[index]
            candidates = self._first_word_map.get(token_lower)
            best_match: Optional[VocabularyEntry] = None
            best_length = 0

            if candidates:
                for entry in candidates:
                    term_length = len(entry.tokens)
                    if term_length > len(word_token_indices) - word_cursor:
                        continue

                    matches = True
                    for offset in range(term_length):
                        compare_token = word_token_indices[word_cursor + offset]
                        if tokens[compare_token]["word_lower"] != entry.tokens[offset]:
                            matches = False
                            break

                    if matches and term_length > best_length:
                        best_match = entry
                        best_length = term_length

            if best_match:
                start_idx = word_token_indices[word_cursor]
                end_idx = word_token_indices[word_cursor + best_length - 1]
                matched_text = "".join(tokens[idx]["text"] for idx in range(start_idx, end_idx + 1))

                if matched_text.strip():
                    anchor = (
                        f'<a href="/word/{best_match.word_id}" '
                        f'class="definition-link">{html.escape(matched_text)}</a>'
                    )
                    spans[start_idx] = (end_idx, anchor)
                    replacements += 1

                word_cursor += best_length
            else:
                word_cursor += 1

        if not spans:
            return None, 0

        parts: List[str] = []
        token_idx = 0
        while token_idx < len(tokens):
            span = spans.get(token_idx)
            if span:
                end_idx, anchor_html = span
                parts.append(anchor_html)
                token_idx = end_idx + 1
                continue

            token_text = tokens[token_idx]["text"]
            parts.append(html.escape(token_text))
            token_idx += 1

        return "".join(parts), replacements


def process_definitions(
    *,
    limit: Optional[int],
    dry_run: bool,
    builder: DefinitionLinkBuilder,
) -> None:
    """Scan vocab.defined and update linkified definitions."""
    scan_sql = """
        SELECT id, definition, definition_with_links
        FROM vocab.defined
        WHERE definition IS NOT NULL
        ORDER BY id
    """
    if limit:
        scan_sql += " LIMIT %s"

    with db_manager.get_cursor() as cursor:
        cursor.execute(scan_sql, (limit,) if limit else None)
        rows = cursor.fetchall()

    total = len(rows)
    updated = 0
    total_links = 0
    batch: List[Tuple[Optional[str], int]] = []

    with db_manager.get_cursor() as cursor:
        for idx, (word_id, definition, existing_html) in enumerate(rows, start=1):
            new_html, replacements = builder.build_html(definition)
            total_links += replacements

            if new_html == existing_html:
                continue

            updated += 1
            batch.append((new_html, word_id))

            if dry_run:
                continue

            if len(batch) >= 500:
                cursor.executemany(
                    "UPDATE vocab.defined SET definition_with_links = %s WHERE id = %s",
                    batch,
                )
                batch.clear()

        if not dry_run and batch:
            cursor.executemany(
                "UPDATE vocab.defined SET definition_with_links = %s WHERE id = %s",
                batch,
            )

    logger.info(
        "Processed %s definitions | %s updated | %s links inserted",
        f"{total:,}",
        f"{updated:,}",
        f"{total_links:,}",
    )
    if dry_run:
        logger.info("Dry run mode: no database changes were committed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Link vocabulary terms within stored definitions.")
    parser.add_argument("--dry-run", action="store_true", help="Compute links without updating the database")
    parser.add_argument(
        "--limit",
        type=int,
        help="Only process the first N definitions (useful for quick experiments)",
    )
    parser.add_argument(
        "--min-term-length",
        type=int,
        default=3,
        help="Minimum number of characters per vocabulary token to consider linkable (default: 3)",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=25,
        help="Maximum number of anchors to inject into a single definition (default: 25)",
    )
    args = parser.parse_args()

    builder = DefinitionLinkBuilder(
        min_term_length=args.min_term_length,
        max_links_per_definition=args.max_links,
    )
    builder.ensure_column()
    builder.load_vocabulary()
    process_definitions(limit=args.limit, dry_run=args.dry_run, builder=builder)


if __name__ == "__main__":
    main()
