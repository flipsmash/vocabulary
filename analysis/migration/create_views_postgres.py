#!/usr/bin/env python3
"""Create PostgreSQL views equivalent to the MySQL views."""

from __future__ import annotations

import os

import psycopg


def main() -> None:
    conn = psycopg.connect(
        host=os.getenv("PGHOST", "10.0.0.99"),
        port=int(os.getenv("PGPORT", "6543")),
        user=os.getenv("PGUSER", "postgres.your-tenant-id"),
        password=os.getenv("PGPASSWORD", "your-super-secret-and-long-postgres-password"),
        dbname=os.getenv("PGDATABASE", "vocab"),
        sslmode=os.getenv("PGSSLMODE", "disable"),
    )

    try:
        conn.autocommit = True
        cur = conn.cursor()

        schema = os.getenv("PGSCHEMA")
        if not schema:
            cur.execute(
                """
                SELECT table_schema
                FROM information_schema.tables
                WHERE table_name = %s
                ORDER BY CASE WHEN table_schema = %s THEN 0 ELSE 1 END, table_schema
                LIMIT 1;
                """,
                ("defined", "vocab"),
            )
            row = cur.fetchone()
            schema = row[0] if row else "public"

        cur.execute(
            f'SET search_path TO "{schema}";',
            prepare=False,
        )
        cur.execute(
            f'DROP VIEW IF EXISTS "{schema}".candidate_review_queue CASCADE;',
            prepare=False,
        )
        cur.execute(
            f'DROP VIEW IF EXISTS "{schema}".harvesting_stats CASCADE;',
            prepare=False,
        )
        cur.execute(
            f'DROP VIEW IF EXISTS "{schema}".defined_missing_definitions CASCADE;',
            prepare=False,
        )
        if schema != "public":
            cur.execute(
                'DROP VIEW IF EXISTS public.defined_missing_definitions CASCADE;',
                prepare=False,
            )

        cur.execute(
            "SELECT to_regclass(%s);",
            (f'"{schema}".candidate_words',),
        )
        candidate_table_exists = cur.fetchone()[0] is not None

        if candidate_table_exists:
            cur.execute(
                f'''
                CREATE VIEW "{schema}".candidate_review_queue AS
                SELECT
                    id,
                    term,
                    source_type,
                    part_of_speech,
                    utility_score,
                    rarity_indicators,
                    context_snippet,
                    raw_definition,
                    etymology_preview,
                    date_discovered,
                    review_status,
                    (CURRENT_DATE - date_discovered) AS days_pending
                FROM "{schema}".candidate_words
                WHERE review_status = 'pending'
                ORDER BY utility_score DESC, date_discovered;
                ''',
                prepare=False,
            )

            cur.execute(
                f'''
                CREATE VIEW "{schema}".harvesting_stats AS
                SELECT
                    source_type,
                    COUNT(*) AS total_candidates,
                    COUNT(*) FILTER (WHERE review_status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE review_status = 'approved') AS approved,
                    COUNT(*) FILTER (WHERE review_status = 'rejected') AS rejected,
                    AVG(utility_score) AS avg_score,
                    MAX(date_discovered) AS last_discovery,
                    MIN(date_discovered) AS first_discovery
                FROM "{schema}".candidate_words
                GROUP BY source_type;
                ''',
                prepare=False,
            )

        cur.execute(
            "SELECT to_regclass(%s);",
            (f'"{schema}".defined',),
        )
        defined_table_exists = cur.fetchone()[0] is not None

        if not defined_table_exists:
            raise RuntimeError(
                f'Base table "{schema}".defined does not exist; cannot create views.'
            )

        cur.execute(
            f'''
            CREATE VIEW "{schema}".defined_missing_definitions AS
            SELECT
                id,
                term,
                part_of_speech,
                definition,
                date_added,
                definition_updated,
                final_rarity
            FROM "{schema}".defined
            WHERE definition IS NULL OR btrim(definition) = '';
            ''',
            prepare=False,
        )

        print('Views created.')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
