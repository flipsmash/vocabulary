"""Tests for the definition filler helper utilities."""

from datetime import datetime, timezone

from core.comprehensive_definition_lookup import Definition, LookupResult
from core.definition_filler import (
    extract_best_definitions,
    map_to_existing_pos,
    normalize_pos,
)


def _lookup_result_for(definitions_by_pos):
    return LookupResult(
        term="sample",
        definitions_by_pos=definitions_by_pos,
        overall_reliability=0.8,
        sources_consulted=["test"],
        lookup_timestamp=datetime.now(timezone.utc),
    )


def test_normalize_pos_trims_and_lowercases():
    assert normalize_pos("  Noun  ") == "noun"
    assert normalize_pos("VERB") == "verb"
    assert normalize_pos(None) is None


def test_map_to_existing_pos_matches_fragments():
    existing = {"noun": "NOUN", "verb": "Verb"}
    assert map_to_existing_pos("noun", existing) == "NOUN"
    assert map_to_existing_pos("Verb, transitive", existing) == "Verb"
    assert map_to_existing_pos("adjective", existing) is None


def test_extract_best_definitions_picks_highest_reliability():
    existing = {"noun": "NOUN", "verb": "Verb"}
    result = _lookup_result_for(
        {
            "noun": [
                Definition(
                    text="first definition",
                    part_of_speech="noun",
                    source="sourceA",
                    source_tier=1,
                    reliability_score=0.4,
                ),
                Definition(
                    text="better definition",
                    part_of_speech="noun",
                    source="sourceB",
                    source_tier=1,
                    reliability_score=0.9,
                ),
            ],
            "Verb / transitive": [
                Definition(
                    text="verb definition",
                    part_of_speech="verb",
                    source="sourceC",
                    source_tier=2,
                    reliability_score=0.7,
                )
            ],
        }
    )

    best = extract_best_definitions(result, existing)

    assert set(best.keys()) == {"NOUN", "Verb"}
    assert best["NOUN"].text == "better definition"
    assert best["Verb"].text == "verb definition"
