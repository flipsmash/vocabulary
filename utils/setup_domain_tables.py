#!/usr/bin/env python3
"""Utility script to initialize domain metadata tables.

Creates the `domains` table (stores domain names and descriptions)
and ensures `word_domains` can reference it via a `domain_id` column.

Run from the repository root:

    source .venv/Scripts/activate  # or your platform equivalent
    python utils/setup_domain_tables.py

"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterable

import mysql.connector
from mysql.connector import Error

# Allow running the script directly from repo root without installing the package
if "core" not in sys.modules:
    import importlib.util
    import pathlib

    config_path = pathlib.Path("core/config.py").resolve()
    spec = importlib.util.spec_from_file_location("core_config", config_path)
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)  # type: ignore[attr-defined]
    get_db_config = config_module.get_db_config
else:  # pragma: no cover - defensive
    from core.config import get_db_config  # type: ignore


@dataclass(frozen=True)
class DomainDefinition:
    name: str
    description: str


DOMAINS: Iterable[DomainDefinition] = (
    DomainDefinition(
        "General / Cross-Domain",
        "Words with broad usage that do not fit a specific specialised discipline.",
    ),
    DomainDefinition(
        "Language & Literature",
        "Linguistics, grammar, rhetoric, and literary forms or devices.",
    ),
    DomainDefinition(
        "Arts & Culture",
        "Visual and performing arts, music, cultural practices, and aesthetics.",
    ),
    DomainDefinition(
        "Life Sciences",
        "Biology, botany, zoology, ecology, and related natural sciences.",
    ),
    DomainDefinition(
        "Medicine & Health Sciences",
        "Anatomy, physiology, clinical practice, pathology, and healthcare terms.",
    ),
    DomainDefinition(
        "Physical Sciences & Engineering",
        "Physics, mechanics, engineering disciplines, instruments, and processes.",
    ),
    DomainDefinition(
        "Chemistry & Materials",
        "Chemical compounds, reactions, materials science, minerals, and alloys.",
    ),
    DomainDefinition(
        "Mathematics & Logic",
        "Mathematical concepts, logic, proofs, and quantitative reasoning.",
    ),
    DomainDefinition(
        "Technology & Computing",
        "Computing, electronics, information technology, and digital systems.",
    ),
    DomainDefinition(
        "Business, Economics & Finance",
        "Commerce, markets, accounting, management, and financial terminology.",
    ),
    DomainDefinition(
        "Law, Government & Civics",
        "Legal systems, political institutions, civic structures, and jurisprudence.",
    ),
    DomainDefinition(
        "Social & Behavioral Sciences",
        "Psychology, sociology, anthropology, culture, and human behavior.",
    ),
    DomainDefinition(
        "Religion, Philosophy & Mythology",
        "Spiritual traditions, philosophical concepts, and mythological references.",
    ),
    DomainDefinition(
        "Geography, Earth & Environment",
        "Geology, geography, climate, natural formations, and environmental science.",
    ),
    DomainDefinition(
        "Maritime & Navigation",
        "Seafaring, naval terminology, navigation techniques, and marine topics.",
    ),
    DomainDefinition(
        "Material Culture & Applied Skills",
        "Culinary arts, agriculture, textiles, craftsmanship, and everyday tools.",
    ),
    DomainDefinition(
        "Military & Security",
        "Armed forces, strategy, weaponry, and security operations.",
    ),
    DomainDefinition(
        "Historical & Archaic Usage",
        "Terms chiefly encountered in historical texts, archaic speech, or obsolete contexts.",
    ),
)


CREATE_DOMAINS_SQL = """
CREATE TABLE IF NOT EXISTS domains (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


ALTER_WORD_DOMAINS_SQL = """
ALTER TABLE word_domains
    ADD COLUMN domain_id INT NULL,
    ADD CONSTRAINT fk_word_domains_domain
        FOREIGN KEY (domain_id) REFERENCES domains(id)
        ON UPDATE CASCADE ON DELETE SET NULL
"""


UPSERT_DOMAINS_SQL = """
INSERT INTO domains (name, description)
VALUES (%s, %s)
ON DUPLICATE KEY UPDATE
    description = VALUES(description),
    updated_at = CURRENT_TIMESTAMP
"""


def ensure_domains_table(cursor) -> None:
    cursor.execute(CREATE_DOMAINS_SQL)


def ensure_word_domains_fk(cursor) -> None:
    cursor.execute("SHOW COLUMNS FROM word_domains LIKE 'domain_id'")
    column_exists = cursor.fetchone() is not None
    if not column_exists:
        cursor.execute(ALTER_WORD_DOMAINS_SQL)


def upsert_domains(cursor) -> int:
    cursor.executemany(
        UPSERT_DOMAINS_SQL,
        [(domain.name, domain.description) for domain in DOMAINS],
    )
    return cursor.rowcount


def main() -> None:
    try:
        conn = mysql.connector.connect(**get_db_config())
        cursor = conn.cursor()

        ensure_domains_table(cursor)
        ensure_word_domains_fk(cursor)
        affected = upsert_domains(cursor)

        conn.commit()

        print("Domain tables are ready.")
        print(f"Inserted/updated domain rows: {affected}")
        print("You can now populate word_domains.domain_id with references to the domains table.")
    except Error as exc:  # pragma: no cover - runtime feedback
        print(f"[ERROR] Database operation failed: {exc}")
        raise
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn.is_connected():
            conn.close()


if __name__ == "__main__":
    main()
