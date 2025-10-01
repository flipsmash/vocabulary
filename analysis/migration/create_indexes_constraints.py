#!/usr/bin/env python3
"""Create indexes and foreign keys in PostgreSQL based on schema metadata."""

from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg


SCHEMA_JSON = Path("analysis/migration/schema_metadata.json")


RULE_MAP = {
    "RESTRICT": None,
    "NO ACTION": "NO ACTION",
    "CASCADE": "CASCADE",
    "SET NULL": "SET NULL",
    "SET DEFAULT": "SET DEFAULT",
}


def format_identifier(name: str) -> str:
    sanitized = name.replace('"', '').replace(' ', '_').lower()
    if len(sanitized) > 60:
        sanitized = sanitized[:60]
    return sanitized


def main() -> None:
    metadata = json.loads(SCHEMA_JSON.read_text())

    schema = os.getenv("PGSCHEMA", "public")

    conn = psycopg.connect(
        host=os.getenv("PGHOST", "10.0.0.99"),
        port=int(os.getenv("PGPORT", "6543")),
        user=os.getenv("PGUSER", "postgres.your-tenant-id"),
        password=os.getenv("PGPASSWORD", "your-super-secret-and-long-postgres-password"),
        dbname=os.getenv("PGDATABASE", "vocab"),
        sslmode=os.getenv("PGSSLMODE", "disable"),
    )

    try:
        conn.autocommit = False
        cur = conn.cursor()

        # Create indexes
        cur.execute(f'SET search_path TO "{schema}";')

        for table_name in sorted(metadata.keys()):
            table = metadata[table_name]
            for index in table.get("indexes", []):
                if not index["columns"]:
                    continue
                columns = ", ".join(f'"{col}"' for col in index["columns"])
                base_name = f"{table_name}_{index['name']}"
                index_name = format_identifier(base_name)
                unique = "UNIQUE " if index["unique"] else ""
                sql = f'CREATE {unique}INDEX IF NOT EXISTS "{index_name}" ON "{schema}"."{table_name}" ({columns});'
                cur.execute(sql)

        # Create foreign keys
        for table_name in sorted(metadata.keys()):
            table = metadata[table_name]
            for fk in table.get("foreign_keys", []):
                columns = ", ".join(f'"{col}"' for col in fk["columns"])
                ref_columns = ", ".join(f'"{col}"' for col in fk["referenced_columns"])
                sql = (
                    f'ALTER TABLE "{schema}"."{table_name}" ADD CONSTRAINT "{fk["name"]}" '
                    f'FOREIGN KEY ({columns}) REFERENCES "{schema}"."{fk["referenced_table"]}" ({ref_columns})'
                )

                delete_rule = RULE_MAP.get(fk["delete_rule"].upper()) if fk.get("delete_rule") else None
                update_rule = RULE_MAP.get(fk["update_rule"].upper()) if fk.get("update_rule") else None
                if delete_rule:
                    sql += f' ON DELETE {delete_rule}'
                if update_rule:
                    sql += f' ON UPDATE {update_rule}'

                sql += ';'
                cur.execute(sql)

        conn.commit()
        print("Indexes and foreign keys created.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
