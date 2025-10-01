#!/usr/bin/env python3
"""Extract MySQL schema metadata and emit PostgreSQL-ready definitions."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

import pymysql

import os
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import VocabularyConfig


OUTPUT_SQL = Path("analysis/migration/postgres_schema.sql")
OUTPUT_JSON = Path("analysis/migration/schema_metadata.json")


@dataclass
class ColumnDef:
    name: str
    data_type: str
    nullable: bool
    default: Optional[str]
    identity: bool


@dataclass
class IndexMeta:
    name: str
    columns: List[str]
    unique: bool


@dataclass
class ForeignKeyMeta:
    name: str
    columns: List[str]
    referenced_table: str
    referenced_columns: List[str]
    update_rule: str
    delete_rule: str


@dataclass
class TableMeta:
    name: str
    columns: List[ColumnDef]
    primary_key: List[str]
    indexes: List[IndexMeta]
    foreign_keys: List[ForeignKeyMeta]


TYPE_MAP = {
    "int": "INTEGER",
    "bigint": "BIGINT",
    "mediumint": "INTEGER",
    "smallint": "SMALLINT",
    "tinyint": "SMALLINT",
    "float": "REAL",
    "double": "DOUBLE PRECISION",
    "double precision": "DOUBLE PRECISION",
    "decimal": "NUMERIC",
    "numeric": "NUMERIC",
    "varchar": "VARCHAR",
    "char": "CHAR",
    "text": "TEXT",
    "mediumtext": "TEXT",
    "longtext": "TEXT",
    "json": "JSONB",
    "datetime": "TIMESTAMP",
    "timestamp": "TIMESTAMP",
    "date": "DATE",
    "time": "TIME",
    "blob": "BYTEA",
    "longblob": "BYTEA",
    "mediumblob": "BYTEA",
}


def map_column_type(row: Dict) -> str:
    data_type = row["DATA_TYPE"].lower()
    column_type = row["COLUMN_TYPE"].lower()

    if data_type == "tinyint" and column_type.startswith("tinyint(1"):
        return "BOOLEAN"

    if data_type in {"varchar", "char"}:
        length = row["CHARACTER_MAXIMUM_LENGTH"]
        return f"{TYPE_MAP[data_type]}({length})"

    if data_type == "decimal" or data_type == "numeric":
        precision = row["NUMERIC_PRECISION"]
        scale = row["NUMERIC_SCALE"]
        return f"NUMERIC({precision}, {scale})"

    if data_type in {"enum", "set"}:
        # Represent enums as TEXT; constraints can be reintroduced later if needed.
        return "TEXT"

    mapped = TYPE_MAP.get(data_type)
    if mapped:
        return mapped

    raise ValueError(f"Unsupported MySQL data type: {row['COLUMN_TYPE']}")


def format_default(row: Dict) -> Optional[str]:
    default = row["COLUMN_DEFAULT"]
    if default is None:
        return None
    if isinstance(default, bytes):
        default = default.decode()
    default_str = str(default)
    lowered = default_str.lower()

    function_defaults = {
        "current_timestamp": "DEFAULT CURRENT_TIMESTAMP",
        "current_timestamp()": "DEFAULT CURRENT_TIMESTAMP",
        "now()": "DEFAULT CURRENT_TIMESTAMP",
        "curdate()": "DEFAULT CURRENT_DATE",
        "current_date": "DEFAULT CURRENT_DATE",
        "current_date()": "DEFAULT CURRENT_DATE",
        "curtime()": "DEFAULT CURRENT_TIME",
        "current_time": "DEFAULT CURRENT_TIME",
        "current_time()": "DEFAULT CURRENT_TIME",
        "utc_timestamp()": "DEFAULT CURRENT_TIMESTAMP",
    }
    if lowered in function_defaults:
        return function_defaults[lowered]

    data_type = row["DATA_TYPE"].lower()
    column_type = row["COLUMN_TYPE"].lower()

    if data_type == "tinyint" and column_type.startswith("tinyint(1"):
        if lowered in {"0", "'0'"}:
            return "DEFAULT FALSE"
        if lowered in {"1", "'1'"}:
            return "DEFAULT TRUE"

    if data_type in {"int", "bigint", "smallint", "mediumint", "tinyint", "float", "double", "decimal", "numeric"}:
        return f"DEFAULT {default_str}"

    # Treat empty string as explicit default.
    escaped = default_str.replace("'", "''")
    return f"DEFAULT '{escaped}'"


def get_primary_key(cursor, table_name: str) -> List[str]:
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM information_schema.key_column_usage
        WHERE table_schema = %s
          AND table_name = %s
          AND constraint_name = 'PRIMARY'
        ORDER BY ORDINAL_POSITION
        """,
        (VocabularyConfig.get_db_config()["database"], table_name),
    )
    return [row["COLUMN_NAME"] for row in cursor.fetchall()]


def populate_indexes(cursor, tables: Dict[str, TableMeta]) -> None:
    cursor.execute(
        """
        SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, COLUMN_NAME, SEQ_IN_INDEX
        FROM information_schema.statistics
        WHERE table_schema = %s
        ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX
        """,
        (VocabularyConfig.get_db_config()["database"],),
    )

    index_map: Dict[tuple[str, str], IndexMeta] = {}

    for row in cursor.fetchall():
        table_name = row["TABLE_NAME"]
        index_name = row["INDEX_NAME"]
        if index_name == "PRIMARY":
            continue

        table = tables.get(table_name)
        if table is None:
            continue

        key = (table_name, index_name)
        if key not in index_map:
            meta = IndexMeta(name=index_name, columns=[], unique=row["NON_UNIQUE"] == 0)
            index_map[key] = meta
            table.indexes.append(meta)

        index_map[key].columns.append(row["COLUMN_NAME"])


def populate_foreign_keys(cursor, tables: Dict[str, TableMeta]) -> None:
    cursor.execute(
        """
        SELECT k.TABLE_NAME,
               k.CONSTRAINT_NAME,
               k.COLUMN_NAME,
               k.ORDINAL_POSITION,
               k.REFERENCED_TABLE_NAME,
               k.REFERENCED_COLUMN_NAME,
               r.UPDATE_RULE,
               r.DELETE_RULE
        FROM information_schema.key_column_usage k
        JOIN information_schema.referential_constraints r
          ON r.constraint_name = k.constraint_name
         AND r.constraint_schema = k.constraint_schema
        WHERE k.table_schema = %s
          AND k.REFERENCED_TABLE_NAME IS NOT NULL
        ORDER BY k.TABLE_NAME, k.CONSTRAINT_NAME, k.ORDINAL_POSITION
        """,
        (VocabularyConfig.get_db_config()["database"],),
    )

    fk_map: Dict[tuple[str, str], ForeignKeyMeta] = {}

    for row in cursor.fetchall():
        table_name = row["TABLE_NAME"]
        constraint_name = row["CONSTRAINT_NAME"]
        referenced_table = row["REFERENCED_TABLE_NAME"]

        table = tables.get(table_name)
        if table is None:
            continue

        key = (table_name, constraint_name)
        if key not in fk_map:
            meta = ForeignKeyMeta(
                name=constraint_name,
                columns=[],
                referenced_table=referenced_table,
                referenced_columns=[],
                update_rule=row["UPDATE_RULE"],
                delete_rule=row["DELETE_RULE"],
            )
            fk_map[key] = meta
            table.foreign_keys.append(meta)

        fk_map[key].columns.append(row["COLUMN_NAME"])
        fk_map[key].referenced_columns.append(row["REFERENCED_COLUMN_NAME"])

def build_table_metadata() -> Dict[str, TableMeta]:
    conn = pymysql.connect(
        **VocabularyConfig.get_db_config(),
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TABLE_NAME, TABLE_TYPE FROM information_schema.tables WHERE table_schema = %s",
            (VocabularyConfig.get_db_config()["database"],),
        )
        table_types = {row["TABLE_NAME"]: row["TABLE_TYPE"] for row in cursor.fetchall()}

        cursor.execute(
            """
            SELECT table_name, column_name, ordinal_position, column_type,
                   data_type, is_nullable, column_default, extra,
                   character_maximum_length, numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_schema = %s
            ORDER BY table_name, ordinal_position
            """,
            (VocabularyConfig.get_db_config()["database"],),
        )

        tables: Dict[str, TableMeta] = {}

        for row in cursor.fetchall():
            table_name = row["TABLE_NAME"]
            if table_types.get(table_name) == "VIEW":
                continue
            column_name = row["COLUMN_NAME"]
            identity = "auto_increment" in ((row["EXTRA"] or "").lower())
            pg_type = map_column_type(row)
            nullable = row["IS_NULLABLE"] == "YES"
            default_clause = format_default(row)
            column_def = ColumnDef(
                name=column_name,
                data_type=pg_type,
                nullable=nullable,
                default=default_clause,
                identity=identity,
            )

            if table_name not in tables:
                tables[table_name] = TableMeta(
                    name=table_name,
                    columns=[],
                    primary_key=[],
                    indexes=[],
                    foreign_keys=[],
                )
            tables[table_name].columns.append(column_def)

        # Primary keys
        for table in tables.values():
            table.primary_key = get_primary_key(cursor, table.name)

        populate_indexes(cursor, tables)
        populate_foreign_keys(cursor, tables)

        return tables
    finally:
        conn.close()


def render_table_sql(meta: TableMeta) -> str:
    column_lines: List[str] = []
    for col in meta.columns:
        pieces = [f'"{col.name}" {col.data_type}']
        if col.identity:
            pieces.append("GENERATED BY DEFAULT AS IDENTITY")
        if not col.nullable:
            pieces.append("NOT NULL")
        if col.default:
            pieces.append(col.default)
        column_lines.append(" ".join(pieces))

    if meta.primary_key:
        pk = ", ".join(f'"{col}"' for col in meta.primary_key)
        column_lines.append(f"PRIMARY KEY ({pk})")

    columns_sql = ",\n    ".join(column_lines)
    return f'CREATE TABLE "{meta.name}" (\n    {columns_sql}\n);'


def main() -> None:
    tables = build_table_metadata()

    ordered_tables = sorted(tables.values(), key=lambda t: t.name)
    sql_statements = [render_table_sql(table) for table in ordered_tables]

    OUTPUT_SQL.write_text("\n\n".join(sql_statements) + "\n")
    OUTPUT_JSON.write_text(
        json.dumps({name: asdict(meta) for name, meta in tables.items()}, indent=2)
    )

    print(f"Wrote {len(sql_statements)} CREATE TABLE statements to {OUTPUT_SQL}")
    print(f"Schema metadata saved to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
