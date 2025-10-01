#!/usr/bin/env python3
"""Stream data from MySQL into PostgreSQL using generated metadata."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Iterable, List

import pymysql
import psycopg


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import VocabularyConfig


SCHEMA_JSON = Path("analysis/migration/schema_metadata.json")
BATCH_SIZE = 20000


def iter_tables(metadata: dict) -> Iterable[dict]:
    # Order tables alphabetically for reproducibility; adjust manually if needed.
    for name in sorted(metadata.keys()):
        yield metadata[name]


def convert_row(row: tuple, columns: List[dict]) -> List:
    converted = []
    for value, column in zip(row, columns):
        if value is None:
            converted.append(None)
            continue

        dtype = column["data_type"].upper()
        if dtype == "BOOLEAN":
            converted.append(bool(value))
        else:
            converted.append(value)
    return converted


def main() -> None:
    metadata = json.loads(SCHEMA_JSON.read_text())

    target_schema = os.getenv("PGSCHEMA", "public")

    mysql_conn = pymysql.connect(
        **VocabularyConfig.get_db_config(),
        cursorclass=pymysql.cursors.SSCursor,
    )
    pg_conn = psycopg.connect(
        host=os.getenv("PGHOST", "10.0.0.99"),
        port=int(os.getenv("PGPORT", "6543")),
        user=os.getenv("PGUSER", "postgres.your-tenant-id"),
        password=os.getenv("PGPASSWORD", "your-super-secret-and-long-postgres-password"),
        dbname=os.getenv("PGDATABASE", "vocab"),
        sslmode=os.getenv("PGSSLMODE", "disable"),
    )

    try:
        pg_conn.autocommit = False
        cur = pg_conn.cursor()
        cur.execute(f'SET search_path TO "{target_schema}";')
        cur.close()

        for table in iter_tables(metadata):
            table_name = table["name"]
            columns = table["columns"]
            column_names = [col["name"] for col in columns]

            mysql_cursor = mysql_conn.cursor()
            mysql_cursor.arraysize = BATCH_SIZE
            select_columns = ", ".join(f"`{name}`" for name in column_names)
            mysql_query = f"SELECT {select_columns} FROM `{table_name}`"
            print(f"Copying {table_name}...")
            mysql_cursor.execute(mysql_query)

            copy_columns = ", ".join(f'"{name}"' for name in column_names)
            copy_sql = f'COPY "{target_schema}"."{table_name}" ({copy_columns}) FROM STDIN WITH (FORMAT text)'

            total_rows = 0
            with pg_conn.cursor().copy(copy_sql) as copy:
                while True:
                    rows = mysql_cursor.fetchmany(BATCH_SIZE)
                    if not rows:
                        break
                    for row in rows:
                        copy.write_row(convert_row(row, columns))
                    total_rows += len(rows)
                    if total_rows % 500000 == 0:
                        print(f"  {table_name}: {total_rows:,} rows copied")

            mysql_cursor.close()
            pg_conn.commit()
            print(f"Finished {table_name}: {total_rows:,} rows")

    finally:
        mysql_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
