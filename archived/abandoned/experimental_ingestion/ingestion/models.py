#!/usr/bin/env python3
"""
Repositories and DB helpers for candidate ingestion tables.

Uses MySQL via mysql.connector and the existing config.get_db_config().
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
import hashlib
import json
import mysql.connector
from datetime import datetime

from config import get_db_config


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Source:
    id: int
    name: str
    type: str
    url: Optional[str]
    license: Optional[str]
    enabled: bool


class CandidateRepo:
    def __init__(self):
        self.db_cfg = get_db_config()

    def get_conn(self):
        return mysql.connector.connect(**self.db_cfg)

    # Schema management -----------------------------------------------------
    def create_tables_if_not_exists(self):
        sql_statements = [
            # sources
            """
            CREATE TABLE IF NOT EXISTS sources (
              id INT AUTO_INCREMENT PRIMARY KEY,
              name VARCHAR(255) NOT NULL,
              type VARCHAR(64) NOT NULL,
              url TEXT NULL,
              license VARCHAR(255) NULL,
              enabled TINYINT(1) NOT NULL DEFAULT 1,
              added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE KEY uniq_name_type (name, type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            # documents
            """
            CREATE TABLE IF NOT EXISTS documents (
              id INT AUTO_INCREMENT PRIMARY KEY,
              source_id INT NOT NULL,
              external_id VARCHAR(255) NULL,
              title TEXT NULL,
              url TEXT NULL,
              published_at DATETIME NULL,
              fetched_at DATETIME NOT NULL,
              hash CHAR(64) NOT NULL,
              lang VARCHAR(8) NULL,
              UNIQUE KEY uniq_source_external (source_id, external_id),
              KEY idx_source_published (source_id, published_at),
              CONSTRAINT fk_documents_source FOREIGN KEY (source_id)
                REFERENCES sources(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            # candidate_terms
            """
            CREATE TABLE IF NOT EXISTS candidate_terms (
              id INT AUTO_INCREMENT PRIMARY KEY,
              lemma VARCHAR(255) NOT NULL,
              display VARCHAR(255) NOT NULL,
              lang VARCHAR(8) NOT NULL DEFAULT 'en',
              pos VARCHAR(32) NULL,
              ngram_len TINYINT NOT NULL DEFAULT 1,
              status ENUM('new','queued','reviewing','promoted','rejected') NOT NULL DEFAULT 'new',
              origin VARCHAR(64) NULL,
              primary_source_id INT NULL,
              origin_sources_json JSON NULL,
              first_seen_at DATETIME NULL,
              created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              UNIQUE KEY uniq_lemma_lang_ngram (lemma, lang, ngram_len),
              KEY idx_status (status),
              CONSTRAINT fk_candidate_primary_source FOREIGN KEY (primary_source_id)
                REFERENCES sources(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            # candidate_observations
            """
            CREATE TABLE IF NOT EXISTS candidate_observations (
              id BIGINT AUTO_INCREMENT PRIMARY KEY,
              candidate_id INT NOT NULL,
              document_id INT NOT NULL,
              token_or_phrase VARCHAR(255) NOT NULL,
              start_idx INT NULL,
              context_snippet VARCHAR(512) NULL,
              observed_at DATETIME NOT NULL,
              KEY idx_candidate (candidate_id),
              CONSTRAINT fk_obs_candidate FOREIGN KEY (candidate_id)
                REFERENCES candidate_terms(id) ON DELETE CASCADE,
              CONSTRAINT fk_obs_document FOREIGN KEY (document_id)
                REFERENCES documents(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            # candidate_metrics
            """
            CREATE TABLE IF NOT EXISTS candidate_metrics (
              candidate_id INT PRIMARY KEY,
              computed_at DATETIME NOT NULL,
              score DOUBLE NULL,
              rarity_z DOUBLE NULL,
              burstiness DOUBLE NULL,
              source_diversity DOUBLE NULL,
              context_diversity DOUBLE NULL,
              novelty DOUBLE NULL,
              length_complexity DOUBLE NULL,
              typo_risk DOUBLE NULL,
              safety_penalty DOUBLE NULL,
              metrics_json JSON NULL,
              CONSTRAINT fk_metrics_candidate FOREIGN KEY (candidate_id)
                REFERENCES candidate_terms(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            # definition_candidates
            """
            CREATE TABLE IF NOT EXISTS definition_candidates (
              id INT AUTO_INCREMENT PRIMARY KEY,
              candidate_id INT NOT NULL,
              source VARCHAR(32) NOT NULL,
              pos VARCHAR(32) NULL,
              gloss TEXT NULL,
              example TEXT NULL,
              sense_key VARCHAR(255) NULL,
              confidence DOUBLE NULL,
              added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              KEY idx_def_cand (candidate_id),
              CONSTRAINT fk_def_candidate FOREIGN KEY (candidate_id)
                REFERENCES candidate_terms(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            # promotions
            """
            CREATE TABLE IF NOT EXISTS promotions (
              id INT AUTO_INCREMENT PRIMARY KEY,
              candidate_id INT NOT NULL,
              term_id INT NULL,
              promoted_at DATETIME NOT NULL,
              notes TEXT NULL,
              KEY idx_prom_cand (candidate_id),
              CONSTRAINT fk_prom_candidate FOREIGN KEY (candidate_id)
                REFERENCES candidate_terms(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            # rejections
            """
            CREATE TABLE IF NOT EXISTS rejections (
              id INT AUTO_INCREMENT PRIMARY KEY,
              candidate_id INT NOT NULL,
              reason_code VARCHAR(64) NULL,
              notes TEXT NULL,
              rejected_at DATETIME NOT NULL,
              KEY idx_rej_cand (candidate_id),
              CONSTRAINT fk_rej_candidate FOREIGN KEY (candidate_id)
                REFERENCES candidate_terms(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            # terms (final lexicon) — do not collide with existing 'defined'; keep separate
            """
            CREATE TABLE IF NOT EXISTS terms (
              id INT AUTO_INCREMENT PRIMARY KEY,
              lemma VARCHAR(255) NOT NULL,
              display VARCHAR(255) NOT NULL,
              lang VARCHAR(8) NOT NULL DEFAULT 'en',
              pos VARCHAR(32) NULL,
              definition TEXT NULL,
              definition_source VARCHAR(64) NULL,
              examples_json JSON NULL,
              pronunciation VARCHAR(255) NULL,
              created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              UNIQUE KEY uniq_terms (lemma, lang)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
        ]

        conn = self.get_conn()
        try:
            cur = conn.cursor()
            for stmt in sql_statements:
                cur.execute(stmt)
            # Ensure unique definition per (candidate_id, pos)
            try:
                cur.execute(
                    """
                    SELECT COUNT(1) FROM information_schema.statistics
                    WHERE table_schema = DATABASE()
                      AND table_name = 'definition_candidates'
                      AND index_name = 'uniq_def_per_pos'
                    """
                )
                exists = cur.fetchone()[0]
                if not exists:
                    cur.execute(
                        "ALTER TABLE definition_candidates ADD UNIQUE KEY uniq_def_per_pos (candidate_id, pos)"
                    )
            except Exception:
                # Ignore if cannot introspect; attempt add and ignore errors
                try:
                    cur.execute(
                        "ALTER TABLE definition_candidates ADD UNIQUE KEY uniq_def_per_pos (candidate_id, pos)"
                    )
                except Exception:
                    pass
            conn.commit()
            cur.close()
        finally:
            conn.close()

    # Source & document upserts --------------------------------------------
    def upsert_source(self, name: str, type_: str, url: Optional[str] = None, license_: Optional[str] = None, enabled: bool = True) -> int:
        conn = self.get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM sources WHERE name=%s AND type=%s",
                (name, type_),
            )
            row = cur.fetchone()
            if row:
                source_id = row[0]
                cur.execute(
                    "UPDATE sources SET url=%s, license=%s, enabled=%s WHERE id=%s",
                    (url, license_, 1 if enabled else 0, source_id),
                )
            else:
                cur.execute(
                    "INSERT INTO sources(name, type, url, license, enabled) VALUES (%s,%s,%s,%s,%s)",
                    (name, type_, url, license_, 1 if enabled else 0),
                )
                source_id = cur.lastrowid
            conn.commit()
            cur.close()
            return source_id
        finally:
            conn.close()

    def upsert_document(
        self,
        source_id: int,
        title: Optional[str],
        url: Optional[str],
        published_at: Optional[datetime],
        external_id: Optional[str] = None,
        lang: Optional[str] = "en",
    ) -> int:
        fetched_at = datetime.utcnow()
        doc_hash = _sha256_hex(f"{external_id or ''}|{title or ''}|{url or ''}")

        conn = self.get_conn()
        try:
            cur = conn.cursor()
            if external_id:
                cur.execute(
                    "SELECT id FROM documents WHERE source_id=%s AND external_id=%s",
                    (source_id, external_id),
                )
                row = cur.fetchone()
            else:
                cur.execute(
                    "SELECT id FROM documents WHERE source_id=%s AND hash=%s",
                    (source_id, doc_hash),
                )
                row = cur.fetchone()

            if row:
                doc_id = row[0]
                cur.execute(
                    "UPDATE documents SET title=%s, url=%s, published_at=%s, fetched_at=%s, hash=%s, lang=%s WHERE id=%s",
                    (title, url, published_at, fetched_at, doc_hash, lang, doc_id),
                )
            else:
                cur.execute(
                    "INSERT INTO documents(source_id, external_id, title, url, published_at, fetched_at, hash, lang) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (source_id, external_id, title, url, published_at, fetched_at, doc_hash, lang),
                )
                doc_id = cur.lastrowid

            conn.commit()
            cur.close()
            return doc_id
        finally:
            conn.close()

    # Candidate & observation upserts --------------------------------------
    def upsert_candidate(
        self,
        lemma: str,
        display: str,
        ngram_len: int,
        pos: Optional[str],
        origin: Optional[str],
        primary_source_id: Optional[int],
        first_seen_at: Optional[datetime] = None,
        origin_sources: Optional[Dict[str, Any]] = None,
    ) -> tuple[int, bool]:
        conn = self.get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM candidate_terms WHERE lemma=%s AND lang='en' AND ngram_len=%s",
                (lemma, ngram_len),
            )
            row = cur.fetchone()
            created = False
            if row:
                cand_id = row[0]
                cur.execute(
                    "UPDATE candidate_terms SET display=%s, pos=%s, origin=%s, primary_source_id=%s, origin_sources_json=%s WHERE id=%s",
                    (
                        display,
                        pos,
                        origin,
                        primary_source_id,
                        json.dumps(origin_sources) if origin_sources else None,
                        cand_id,
                    ),
                )
            else:
                cur.execute(
                    "INSERT INTO candidate_terms(lemma, display, lang, pos, ngram_len, status, origin, primary_source_id, origin_sources_json, first_seen_at) VALUES (%s,%s,'en',%s,%s,'new',%s,%s,%s,%s)",
                    (
                        lemma,
                        display,
                        pos,
                        ngram_len,
                        origin,
                        primary_source_id,
                        json.dumps(origin_sources) if origin_sources else None,
                        first_seen_at or datetime.utcnow(),
                    ),
                )
                cand_id = cur.lastrowid
                created = True
            conn.commit()
            cur.close()
            return cand_id, created
        finally:
            conn.close()

    def add_observation(
        self,
        candidate_id: int,
        document_id: int,
        token_or_phrase: str,
        start_idx: Optional[int],
        context_snippet: Optional[str],
        observed_at: Optional[datetime] = None,
    ) -> int:
        conn = self.get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO candidate_observations(candidate_id, document_id, token_or_phrase, start_idx, context_snippet, observed_at) VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    candidate_id,
                    document_id,
                    token_or_phrase,
                    start_idx,
                    (context_snippet or "")[:512],
                    observed_at or datetime.utcnow(),
                ),
            )
            obs_id = cur.lastrowid
            conn.commit()
            cur.close()
            return obs_id
        finally:
            conn.close()

    def upsert_metrics(self, candidate_id: int, metrics: Dict[str, Any]):
        conn = self.get_conn()
        try:
            cur = conn.cursor()
            fields = [
                "score",
                "rarity_z",
                "burstiness",
                "source_diversity",
                "context_diversity",
                "novelty",
                "length_complexity",
                "typo_risk",
                "safety_penalty",
            ]
            values = [metrics.get(k) for k in fields]
            cur.execute("SELECT candidate_id FROM candidate_metrics WHERE candidate_id=%s", (candidate_id,))
            if cur.fetchone():
                cur.execute(
                    "UPDATE candidate_metrics SET computed_at=%s, score=%s, rarity_z=%s, burstiness=%s, source_diversity=%s, context_diversity=%s, novelty=%s, length_complexity=%s, typo_risk=%s, safety_penalty=%s, metrics_json=%s WHERE candidate_id=%s",
                    (
                        datetime.utcnow(),
                        *values,
                        json.dumps(metrics),
                        candidate_id,
                    ),
                )
            else:
                cur.execute(
                    "INSERT INTO candidate_metrics(candidate_id, computed_at, score, rarity_z, burstiness, source_diversity, context_diversity, novelty, length_complexity, typo_risk, safety_penalty, metrics_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        candidate_id,
                        datetime.utcnow(),
                        *values,
                        json.dumps(metrics),
                    ),
                )
            conn.commit()
            cur.close()
        finally:
            conn.close()

    # Queries for UI --------------------------------------------------------
    def list_candidates(
        self,
        status: Optional[str] = None,
        min_score: Optional[float] = None,
        q: Optional[str] = None,
        pos: Optional[str] = None,
        ngram_len: Optional[int] = None,
        origin: Optional[str] = None,
        page: int = 1,
        size: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        offset = (page - 1) * size
        where = ["1=1"]
        params: List[Any] = []
        if status:
            where.append("ct.status=%s")
            params.append(status)
        if q:
            where.append("(ct.lemma LIKE %s OR ct.display LIKE %s)")
            params.extend([f"%{q}%", f"%{q}%"])
        if pos:
            where.append("ct.pos=%s")
            params.append(pos)
        if ngram_len:
            where.append("ct.ngram_len=%s")
            params.append(ngram_len)
        if origin:
            where.append("ct.origin=%s")
            params.append(origin)
        if min_score is not None:
            where.append("(cm.score IS NULL OR cm.score >= %s)")
            params.append(min_score)
        where_sql = " AND ".join(where)

        conn = self.get_conn()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                f"""
                SELECT SQL_CALC_FOUND_ROWS
                    ct.id, ct.lemma, ct.display, ct.pos, ct.ngram_len, ct.status, ct.origin,
                    cm.score, cm.metrics_json,
                    ct.created_at, ct.updated_at
                FROM candidate_terms ct
                LEFT JOIN candidate_metrics cm ON cm.candidate_id = ct.id
                WHERE {where_sql}
                ORDER BY COALESCE(cm.score, -9999) DESC, ct.created_at DESC
                LIMIT %s OFFSET %s
                """,
                (*params, size, offset),
            )
            rows = cur.fetchall()
            cur.execute("SELECT FOUND_ROWS() AS total")
            total = cur.fetchone()["total"]
            cur.close()
            return rows, int(total)
        finally:
            conn.close()

    def get_candidate_detail(self, candidate_id: int) -> Dict[str, Any]:
        conn = self.get_conn()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT ct.*, cm.score, cm.metrics_json
                FROM candidate_terms ct
                LEFT JOIN candidate_metrics cm ON cm.candidate_id = ct.id
                WHERE ct.id=%s
                """,
                (candidate_id,),
            )
            cand = cur.fetchone()
            if not cand:
                cur.close()
                return {}
            cur.execute(
                "SELECT dc.* FROM definition_candidates dc WHERE dc.candidate_id=%s ORDER BY confidence DESC, id ASC",
                (candidate_id,),
            )
            defs = cur.fetchall()
            cur.execute(
                """
                SELECT co.*, d.title, d.url FROM candidate_observations co
                JOIN documents d ON d.id = co.document_id
                WHERE co.candidate_id=%s ORDER BY co.observed_at DESC LIMIT 100
                """,
                (candidate_id,),
            )
            obs = cur.fetchall()
            cur.close()
            return {"candidate": cand, "definitions": defs, "observations": obs}
        finally:
            conn.close()

    def update_candidate_status(self, candidate_id: int, status: str):
        conn = self.get_conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE candidate_terms SET status=%s WHERE id=%s", (status, candidate_id))
            conn.commit()
            cur.close()
        finally:
            conn.close()

    def promote_candidate(self, candidate_id: int, definition_id: Optional[int], notes: Optional[str]) -> int:
        # Fetch candidate
        detail = self.get_candidate_detail(candidate_id)
        cand = detail.get("candidate") or {}
        if not cand:
            raise ValueError("Candidate not found")
        definition_text = None
        definition_source = None
        if definition_id:
            for d in detail.get("definitions", []):
                if d["id"] == definition_id:
                    definition_text = d.get("gloss")
                    definition_source = d.get("source")
                    break
        conn = self.get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO terms(lemma, display, lang, pos, definition, definition_source) VALUES (%s,%s,'en',%s,%s,%s)",
                (
                    cand.get("lemma"),
                    cand.get("display"),
                    cand.get("pos"),
                    definition_text,
                    definition_source,
                ),
            )
            term_id = cur.lastrowid
            cur.execute(
                "INSERT INTO promotions(candidate_id, term_id, promoted_at, notes) VALUES (%s,%s,%s,%s)",
                (candidate_id, term_id, datetime.utcnow(), notes),
            )
            cur.execute("UPDATE candidate_terms SET status='promoted' WHERE id=%s", (candidate_id,))
            conn.commit()
            cur.close()
            return term_id
        finally:
            conn.close()
