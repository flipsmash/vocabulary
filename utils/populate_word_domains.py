#!/usr/bin/env python3
"""Populate `word_domains` with primary domains inferred from definitions."""

from __future__ import annotations

import importlib.util
import pathlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

import mysql.connector
from mysql.connector import Error

# Lazy import of get_db_config without importing the whole core package
CONFIG_PATH = pathlib.Path("core/config.py").resolve()
spec = importlib.util.spec_from_file_location("core_config", CONFIG_PATH)
config_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config_module)  # type: ignore[attr-defined]
get_db_config = config_module.get_db_config  # type: ignore[attr-defined]


@dataclass(frozen=True)
class DomainRule:
    domain_name: str
    keywords: Tuple[str, ...]


DOMAIN_RULES: Iterable[DomainRule] = (
    DomainRule(
        "Language & Literature",
        (
            "linguistic",
            "grammar",
            "language",
            "speech",
            "dialect",
            "etymology",
            "poetic",
            "rhetoric",
            "stanza",
            "sonnet",
        ),
    ),
    DomainRule(
        "Arts & Culture",
        (
            "music",
            "melody",
            "rhythm",
            "art",
            "painting",
            "sculpture",
            "theatre",
            "dance",
            "opera",
            "folklore",
        ),
    ),
    DomainRule(
        "Life Sciences",
        (
            "biology",
            "botany",
            "zoology",
            "plant",
            "animal",
            "species",
            "genus",
            "organism",
            "ecology",
            "flora",
            "fauna",
        ),
    ),
    DomainRule(
        "Medicine & Health Sciences",
        (
            "medicine",
            "medical",
            "anatomy",
            "disease",
            "therapy",
            "surgery",
            "clinical",
            "pathology",
            "physiology",
            "pharmac",
            "syndrome",
        ),
    ),
    DomainRule(
        "Physical Sciences & Engineering",
        (
            "physics",
            "force",
            "mechanical",
            "energy",
            "instrument",
            "engineering",
            "machine",
            "device",
            "lever",
            "momentum",
        ),
    ),
    DomainRule(
        "Chemistry & Materials",
        (
            "chemistry",
            "chemical",
            "compound",
            "reagent",
            "mineral",
            "crystal",
            "alloy",
            "element",
            "solvent",
            "precipitate",
        ),
    ),
    DomainRule(
        "Mathematics & Logic",
        (
            "mathemat",
            "algebra",
            "geometry",
            "equation",
            "number",
            "calculus",
            "probability",
            "logic",
            "axiom",
            "theorem",
        ),
    ),
    DomainRule(
        "Technology & Computing",
        (
            "computer",
            "software",
            "digital",
            "electronic",
            "network",
            "program",
            "algorithm",
            "database",
            "cyber",
            "robot",
        ),
    ),
    DomainRule(
        "Business, Economics & Finance",
        (
            "business",
            "finance",
            "economic",
            "market",
            "trade",
            "commerce",
            "account",
            "bank",
            "capital",
            "budget",
        ),
    ),
    DomainRule(
        "Law, Government & Civics",
        (
            "law",
            "legal",
            "court",
            "government",
            "politic",
            "parliament",
            "constitution",
            "judicial",
            "civic",
            "statute",
        ),
    ),
    DomainRule(
        "Social & Behavioral Sciences",
        (
            "sociolog",
            "psycholog",
            "anthropolog",
            "behavior",
            "culture",
            "social",
            "habit",
            "demograph",
        ),
    ),
    DomainRule(
        "Religion, Philosophy & Mythology",
        (
            "religion",
            "religious",
            "theolog",
            "philosoph",
            "mytholog",
            "spiritual",
            "metaphys",
            "doctrine",
        ),
    ),
    DomainRule(
        "Geography, Earth & Environment",
        (
            "geolog",
            "geograph",
            "climate",
            "terrain",
            "mountain",
            "river",
            "valley",
            "soil",
            "atmosphere",
            "erosion",
        ),
    ),
    DomainRule(
        "Maritime & Navigation",
        (
            "ship",
            "naval",
            "nautical",
            "sail",
            "marine",
            "seafaring",
            "harbor",
            "vessel",
            "helm",
            "keel",
        ),
    ),
    DomainRule(
        "Material Culture & Applied Skills",
        (
            "textile",
            "fabric",
            "weave",
            "garment",
            "culinary",
            "cooking",
            "food",
            "agricultur",
            "farming",
            "tool",
            "craft",
        ),
    ),
    DomainRule(
        "Military & Security",
        (
            "militar",
            "army",
            "navy",
            "weapon",
            "battle",
            "combat",
            "defense",
            "fort",
            "tactic",
            "strategy",
        ),
    ),
    DomainRule(
        "Historical & Archaic Usage",
        (
            "archaic",
            "obsolete",
            "historical",
            "old-fashioned",
            "antiqu",
            "former times",
            "antiquated",
        ),
    ),
)


def fetch_domain_id_map(cursor) -> Dict[str, int]:
    cursor.execute("SELECT id, name FROM vocab.domains")
    return {name.lower(): domain_id for domain_id, name in cursor.fetchall()}


def choose_domain(definition: str, rules: Dict[str, Tuple[str, ...]]) -> str:
    text = definition.lower()
    scores = defaultdict(int)
    for domain, keywords in rules.items():
        for keyword in keywords:
            if keyword in text:
                scores[domain] += 1
    if not scores:
        return "General / Cross-Domain"
    return max(scores.items(), key=lambda item: item[1])[0]


def main() -> None:
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(**get_db_config())
        cursor = conn.cursor()

        domain_map = fetch_domain_id_map(cursor)
        keyword_map = {rule.domain_name: rule.keywords for rule in DOMAIN_RULES}

        cursor.execute(
            "SELECT id, COALESCE(definition, '') FROM vocab.defined"
        )
        rows = cursor.fetchall()

        updates: List[Tuple[int, str, int]] = []

        for word_id, definition in rows:
            chosen_domain = choose_domain(definition, keyword_map)

            domain_id = domain_map.get(chosen_domain.lower())
            if domain_id is None:
                domain_id = domain_map.get("general / cross-domain")

            updates.append((word_id, chosen_domain or "General / Cross-Domain", domain_id))

        cursor.executemany(
            """
            INSERT INTO vocab.word_domains (word_id, primary_domain, domain_id)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                primary_domain = VALUES(primary_domain),
                domain_id = VALUES(domain_id)
            """,
            updates,
        )
        conn.commit()
        print(f"Domain assignments updated: {cursor.rowcount}")

    except Error as exc:
        print(f"[ERROR] Failed to populate word domains: {exc}")
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None and conn.is_connected():
            conn.close()


if __name__ == "__main__":
    main()
