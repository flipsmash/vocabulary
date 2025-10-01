#!/usr/bin/env python3
"""Utilities for filling missing definitions and parts of speech.

This module provides the core logic used by the CLI to repair entries in the
``defined`` table that are missing definitions and/or part-of-speech tags. It
leans on :class:`core.comprehensive_definition_lookup.ComprehensiveDefinitionLookup`
so we reuse the existing multi-source definition pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core.comprehensive_definition_lookup import (
    ComprehensiveDefinitionLookup,
    Definition,
    LookupResult,
)
from core.database_manager import database_cursor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data containers used during filling


@dataclass(slots=True)
class MissingDefinitionRow:
    """Represents a row in ``defined`` lacking a definition."""

    id: int
    term: str
    part_of_speech: Optional[str]


@dataclass(slots=True)
class UpdateAction:
    """Definition update to apply to an existing row."""

    row_id: int
    term: str
    part_of_speech: Optional[str]
    definition_text: str
    definition_source: Optional[str]


@dataclass(slots=True)
class InsertAction:
    """Definition insert for an additional part of speech."""

    term: str
    part_of_speech: Optional[str]
    definition_text: str
    definition_source: Optional[str]


@dataclass(slots=True)
class FillSummary:
    """Lightweight summary of a filling run."""

    looked_up: int = 0
    updated: int = 0
    inserted: int = 0
    skipped: int = 0


# ---------------------------------------------------------------------------
# POS utilities – kept simple so we can unit-test them without hitting the DB


def normalize_pos(pos: Optional[str]) -> Optional[str]:
    """Normalize a part-of-speech label for matching.

    We trim whitespace, collapse repeated spaces, and lowercase the value so we
    can safely compare against other POS labels in a case-insensitive manner.
    """

    if not pos:
        return None

    collapsed = re.sub(r"\s+", " ", pos.strip())
    return collapsed.lower() if collapsed else None


def map_to_existing_pos(
    pos: Optional[str],
    existing_pos_map: Dict[str, str],
) -> Optional[str]:
    """Map a POS label to the canonical form already stored in ``defined``.

    The ``existing_pos_map`` should map normalized (lower-case) POS labels to
    the exact string stored in the database. We attempt several fallbacks so we
    can handle slightly more verbose labels (e.g., ``"Verb, transitive"``).
    """

    norm = normalize_pos(pos)
    if not norm:
        return None

    if norm in existing_pos_map:
        return existing_pos_map[norm]

    # Split on punctuation and the word "or" to find a recognizable fragment
    for fragment in re.split(r"[;,/]|\bor\b", norm):
        fragment = fragment.strip()
        if fragment and fragment in existing_pos_map:
            return existing_pos_map[fragment]

    return None


def extract_best_definitions(
    lookup_result: LookupResult,
    existing_pos_map: Dict[str, str],
) -> Dict[str, Definition]:
    """Build a mapping of canonical POS -> highest reliability definition."""

    best_by_pos: Dict[str, Definition] = {}

    for pos_label, definitions in lookup_result.definitions_by_pos.items():
        canonical = map_to_existing_pos(pos_label, existing_pos_map)
        if not canonical or not definitions:
            continue

        # Pick the most reliable definition for this POS
        best_definition = max(
            definitions,
            key=lambda definition: definition.reliability_score,
        )

        current_best = best_by_pos.get(canonical)
        if not current_best or best_definition.reliability_score > current_best.reliability_score:
            best_by_pos[canonical] = best_definition

    return best_by_pos


# ---------------------------------------------------------------------------
# Database helpers


def _fetch_existing_pos_values() -> Dict[str, str]:
    """Return a mapping of normalized POS labels to their canonical form."""

    with database_cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT part_of_speech
            FROM defined
            WHERE part_of_speech IS NOT NULL
              AND TRIM(part_of_speech) != ''
            """
        )
        rows = cursor.fetchall()

    pos_map: Dict[str, str] = {}
    for (pos_value,) in rows:
        canonical = pos_value.strip()
        norm = normalize_pos(canonical)
        if canonical and norm and norm not in pos_map:
            pos_map[norm] = canonical

    return pos_map


def _load_missing_rows(limit: Optional[int]) -> List[MissingDefinitionRow]:
    """Load rows that need to be filled."""

    query = (
        "SELECT id, term, part_of_speech "
        "FROM defined "
        "WHERE definition IS NULL OR TRIM(definition) = '' "
        "ORDER BY id ASC"
    )

    params: Sequence[Any] = ()
    if limit is not None:
        query += " LIMIT %s"
        params = (int(limit),)

    with database_cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

    missing_rows: List[MissingDefinitionRow] = []
    for row_id, term, part_of_speech in rows:
        if not term:
            continue
        missing_rows.append(
            MissingDefinitionRow(
                id=row_id,
                term=term.strip(),
                part_of_speech=part_of_speech.strip() if part_of_speech else None,
            )
        )

    return missing_rows


def _fetch_existing_filled_keys(existing_pos_map: Dict[str, str]) -> set[Tuple[str, str]]:
    """Return the set of (term, pos) combinations that already have definitions."""

    keys: set[Tuple[str, str]] = set()

    with database_cursor() as cursor:
        cursor.execute(
            """
            SELECT LOWER(term), part_of_speech
            FROM defined
            WHERE definition IS NOT NULL
              AND TRIM(definition) != ''
            """
        )
        for term_lower, pos_value in cursor.fetchall():
            canonical = map_to_existing_pos(pos_value, existing_pos_map)
            if term_lower and canonical:
                keys.add((term_lower, normalize_pos(canonical) or canonical.lower()))

    return keys


async def _lookup_terms(terms: Iterable[str]) -> Dict[str, LookupResult]:
    """Perform asynchronous lookups for the provided terms."""

    results: Dict[str, LookupResult] = {}
    async with ComprehensiveDefinitionLookup() as lookup:
        for term in terms:
            try:
                lookup_result = await lookup.lookup_term(term, use_cache=True)
                results[term.lower()] = lookup_result
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Definition lookup failed for '%s': %s", term, exc)

    return results


def _prepare_actions_for_term(
    term_rows: List[MissingDefinitionRow],
    definitions_by_pos: Dict[str, Definition],
    existing_pos_map: Dict[str, str],
    existing_filled_keys: set[Tuple[str, str]],
) -> Tuple[List[UpdateAction], List[InsertAction], int]:
    """Create update/insert actions for a single term.

    Returns a tuple of (updates, inserts, skipped_count).
    """

    updates: List[UpdateAction] = []
    inserts: List[InsertAction] = []
    skipped = 0

    if not definitions_by_pos:
        return updates, inserts, len(term_rows)

    available_defs = dict(definitions_by_pos)

    # First, update rows that already specify a POS.
    for row in term_rows:
        if not row.part_of_speech:
            continue

        canonical_pos = map_to_existing_pos(row.part_of_speech, existing_pos_map)
        if not canonical_pos:
            logger.warning(
                "Skipping row %s (%s): part of speech '%s' not recognised",
                row.id,
                row.term,
                row.part_of_speech,
            )
            skipped += 1
            continue

        best_definition = available_defs.get(canonical_pos)
        if not best_definition:
            logger.info(
                "No definition found for %s as %s (row %s)",
                row.term,
                canonical_pos,
                row.id,
            )
            skipped += 1
            continue

        updates.append(
            UpdateAction(
                row_id=row.id,
                term=row.term,
                part_of_speech=canonical_pos,
                definition_text=best_definition.text,
                definition_source=best_definition.source,
            )
        )

        key = (row.term.lower(), normalize_pos(canonical_pos) or canonical_pos.lower())
        existing_filled_keys.add(key)
        available_defs.pop(canonical_pos, None)

    # Next, handle rows without a POS by assigning the most reliable definitions
    leftover_defs = sorted(
        available_defs.items(),
        key=lambda item: item[1].reliability_score,
        reverse=True,
    )

    rows_without_pos = [row for row in term_rows if row.part_of_speech is None]
    assigned_pairs = list(zip(rows_without_pos, leftover_defs))

    for row, (pos_label, definition) in assigned_pairs:
        updates.append(
            UpdateAction(
                row_id=row.id,
                term=row.term,
                part_of_speech=pos_label,
                definition_text=definition.text,
                definition_source=definition.source,
            )
        )

        key = (row.term.lower(), normalize_pos(pos_label) or pos_label.lower())
        existing_filled_keys.add(key)

    # Determine which definitions remain unused after updating existing rows.
    used_defs_count = len(assigned_pairs)
    remaining_defs = leftover_defs[used_defs_count:]

    for pos_label, definition in remaining_defs:
        key = (term_rows[0].term.lower(), normalize_pos(pos_label) or pos_label.lower())
        if key in existing_filled_keys:
            continue

        inserts.append(
            InsertAction(
                term=term_rows[0].term,
                part_of_speech=pos_label,
                definition_text=definition.text,
                definition_source=definition.source,
            )
        )
        existing_filled_keys.add(key)

    assigned_rows = [row for row in term_rows if any(action.row_id == row.id for action in updates)]
    skipped += len(term_rows) - len(assigned_rows)

    return updates, inserts, skipped


def _apply_updates(
    updates: List[UpdateAction],
    available_columns: set[str],
) -> int:
    """Persist updates to existing rows."""

    if not updates:
        return 0

    updated_rows = 0
    with database_cursor() as cursor:
        for action in updates:
            set_clauses = ["definition = %s"]
            params: List[Any] = [action.definition_text]

            if action.part_of_speech:
                set_clauses.append("part_of_speech = %s")
                params.append(action.part_of_speech)

            if action.definition_source and "definition_source" in available_columns:
                set_clauses.append("definition_source = %s")
                params.append(action.definition_source)

            params.append(action.row_id)
            sql = f"UPDATE defined SET {', '.join(set_clauses)} WHERE id = %s"
            cursor.execute(sql, params)
            updated_rows += cursor.rowcount

    return updated_rows


def _apply_inserts(
    inserts: List[InsertAction],
    available_columns: set[str],
) -> int:
    """Persist newly created rows for additional parts of speech."""

    if not inserts:
        return 0

    inserted_rows = 0
    column_names = ["term", "definition"]
    if "part_of_speech" in available_columns:
        column_names.append("part_of_speech")
    if "definition_source" in available_columns:
        column_names.append("definition_source")
    if "date_added" in available_columns:
        column_names.append("date_added")

    placeholders = ", ".join(["%s"] * len(column_names))
    insert_sql = f"INSERT INTO defined ({', '.join(column_names)}) VALUES ({placeholders})"

    with database_cursor() as cursor:
        for action in inserts:
            params: List[Any] = [action.term, action.definition_text]

            if "part_of_speech" in available_columns:
                params.append(action.part_of_speech)
            if "definition_source" in available_columns:
                params.append(action.definition_source)
            if "date_added" in available_columns:
                params.append(date.today())

            cursor.execute(insert_sql, params)
            inserted_rows += cursor.rowcount

    return inserted_rows


def _fetch_defined_columns() -> set[str]:
    with database_cursor() as cursor:
        cursor.execute("SHOW COLUMNS FROM defined")
        columns = {row[0] for row in cursor.fetchall()}
    return columns


def fill_missing_definitions(
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> FillSummary:
    """Fill missing definitions and part-of-speech data.

    Args:
        limit: Optional limit on the number of rows processed in this run.
        dry_run: When ``True`` we only log the actions without mutating the DB.

    Returns:
        :class:`FillSummary` describing the performed actions.
    """

    summary = FillSummary()

    existing_pos_map = _fetch_existing_pos_values()
    missing_rows = _load_missing_rows(limit)

    if not missing_rows:
        logger.info("No definitions to fill – everything looks good!")
        return summary

    terms_to_lookup = sorted({row.term for row in missing_rows})
    summary.looked_up = len(terms_to_lookup)
    lookup_results = asyncio.run(_lookup_terms(terms_to_lookup))

    existing_filled_keys = _fetch_existing_filled_keys(existing_pos_map)

    updates: List[UpdateAction] = []
    inserts: List[InsertAction] = []
    total_skipped = 0

    rows_by_term: Dict[str, List[MissingDefinitionRow]] = {}
    for row in missing_rows:
        rows_by_term.setdefault(row.term.lower(), []).append(row)

    for term_lower, rows in rows_by_term.items():
        lookup_result = lookup_results.get(term_lower)
        if not lookup_result:
            total_skipped += len(rows)
            logger.info("Skipping %s rows for '%s': lookup unavailable", len(rows), rows[0].term)
            continue

        definitions_by_pos = extract_best_definitions(lookup_result, existing_pos_map)
        term_updates, term_inserts, term_skipped = _prepare_actions_for_term(
            rows,
            definitions_by_pos,
            existing_pos_map,
            existing_filled_keys,
        )

        updates.extend(term_updates)
        inserts.extend(term_inserts)
        total_skipped += term_skipped

    summary.skipped = total_skipped

    if dry_run:
        for action in updates:
            logger.info(
                "[DRY RUN] Would update row %s ('%s', POS=%s) with definition from %s",
                action.row_id,
                action.term,
                action.part_of_speech,
                action.definition_source or "unknown source",
            )
        for action in inserts:
            logger.info(
                "[DRY RUN] Would insert new row for '%s' (%s) from %s",
                action.term,
                action.part_of_speech,
                action.definition_source or "unknown source",
            )
        return summary

    available_columns = _fetch_defined_columns()

    summary.updated = _apply_updates(updates, available_columns)
    summary.inserted = _apply_inserts(inserts, available_columns)

    logger.info(
        "Filled definitions: %s updated, %s inserted, %s skipped",
        summary.updated,
        summary.inserted,
        summary.skipped,
    )

    return summary


__all__ = [
    "fill_missing_definitions",
    "normalize_pos",
    "map_to_existing_pos",
    "extract_best_definitions",
]
