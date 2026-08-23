"""SQLite-backed StorageRepository for CYNTHERA domain objects.

Persists Hypothesis, RetrievalPackage, and ReasoningResult using
SQLite with JSON column values. Requires no external ORM — uses
Python's built-in sqlite3 module.

Reference: 06_DATABASE_SPECIFICATION.md (adapted for SQLite)
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.core.domain.hypothesis import Hypothesis
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.reasoning_result import ReasoningResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# DDL — Table Definitions
# ─────────────────────────────────────────────

_DDL_HYPOTHESES = """
CREATE TABLE IF NOT EXISTS hypotheses (
    id TEXT PRIMARY KEY,
    drug_name TEXT NOT NULL,
    disease_name TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL,
    retrieval_policy TEXT NOT NULL,
    trace_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_message TEXT,
    data_json TEXT NOT NULL
);
"""

_DDL_RETRIEVAL_PACKAGES = """
CREATE TABLE IF NOT EXISTS retrieval_packages (
    id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL,
    retrieval_confidence TEXT NOT NULL,
    sources_queried_json TEXT NOT NULL,
    sources_failed_json TEXT NOT NULL,
    sealed_at TEXT NOT NULL,
    data_json TEXT NOT NULL,
    FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(id)
);
"""

_DDL_REASONING_RESULTS = """
CREATE TABLE IF NOT EXISTS reasoning_results (
    id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL,
    recommendation_status TEXT NOT NULL,
    support_score REAL NOT NULL,
    mechanistic_score REAL NOT NULL,
    risk_score REAL NOT NULL,
    rule_set_version TEXT NOT NULL,
    reasoning_duration_ms REAL NOT NULL,
    completed_at TEXT NOT NULL,
    data_json TEXT NOT NULL,
    FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(id)
);
"""

_DDL_EVALUATIONS_VIEW = """
CREATE VIEW IF NOT EXISTS evaluations AS
    SELECT
        h.id          AS hypothesis_id,
        h.drug_name,
        h.disease_name,
        h.lifecycle_state,
        h.created_at,
        rr.recommendation_status AS recommendation,
        rr.support_score,
        rr.mechanistic_score,
        rr.risk_score,
        rr.completed_at,
        rp.retrieval_confidence,
        rp.sources_queried_json
    FROM hypotheses h
    LEFT JOIN reasoning_results rr ON rr.hypothesis_id = h.id
    LEFT JOIN retrieval_packages rp ON rp.hypothesis_id = h.id;
"""


class StorageRepository:
    """SQLite-backed repository for persisting CYNTHERA domain objects.

    Thread-safe via check_same_thread=False; uses a connection-per-call
    approach appropriate for single-process use. Each method opens and
    closes a connection to avoid long-lived connections leaking in async
    contexts.

    Args:
        db_path: File path for the SQLite database. Directories will be
            created automatically.
    """

    def __init__(self, db_path: str = "data/cynthera.db") -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ─────────────────────────────────────────────
    # Internal Helpers
    # ─────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        """Open a new SQLite connection with JSON support."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_schema(self) -> None:
        """Create tables and view if they do not exist."""
        with self._connect() as conn:
            conn.execute(_DDL_HYPOTHESES)
            conn.execute(_DDL_RETRIEVAL_PACKAGES)
            conn.execute(_DDL_REASONING_RESULTS)
            try:
                conn.execute(_DDL_EVALUATIONS_VIEW)
            except sqlite3.OperationalError:
                pass  # View already exists — ignore
            conn.commit()
        logger.debug("storage_schema_initialized", extra={"db_path": self._db_path})

    # ─────────────────────────────────────────────
    # Hypothesis
    # ─────────────────────────────────────────────

    def save_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Persist or update a Hypothesis record (upsert).

        Args:
            hypothesis: The Hypothesis domain object to persist.
        """
        data_json = hypothesis.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO hypotheses
                    (id, drug_name, disease_name, lifecycle_state, retrieval_policy,
                     trace_id, created_at, updated_at, error_message, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    lifecycle_state = excluded.lifecycle_state,
                    updated_at      = excluded.updated_at,
                    error_message   = excluded.error_message,
                    data_json       = excluded.data_json
                """,
                (
                    str(hypothesis.id),
                    hypothesis.drug_name,
                    hypothesis.disease_name,
                    hypothesis.lifecycle_state.value,
                    hypothesis.retrieval_policy.value,
                    str(hypothesis.trace_id),
                    hypothesis.created_at.isoformat(),
                    hypothesis.updated_at.isoformat(),
                    hypothesis.error_message,
                    data_json,
                ),
            )
            conn.commit()
        logger.debug("hypothesis_saved", extra={"hypothesis_id": str(hypothesis.id)})

    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis | None:
        """Retrieve a Hypothesis by ID.

        Args:
            hypothesis_id: UUID string of the hypothesis.

        Returns:
            Hypothesis domain object, or None if not found.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json FROM hypotheses WHERE id = ?",
                (hypothesis_id,),
            ).fetchone()
        if row is None:
            return None
        return Hypothesis.model_validate_json(row["data_json"])

    # ─────────────────────────────────────────────
    # RetrievalPackage
    # ─────────────────────────────────────────────

    def save_retrieval_package(self, package: RetrievalPackage) -> None:
        """Persist a RetrievalPackage record (upsert).

        Args:
            package: The RetrievalPackage domain object to persist.
        """
        data_json = package.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO retrieval_packages
                    (id, hypothesis_id, retrieval_confidence,
                     sources_queried_json, sources_failed_json,
                     sealed_at, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    retrieval_confidence  = excluded.retrieval_confidence,
                    sources_queried_json  = excluded.sources_queried_json,
                    sources_failed_json   = excluded.sources_failed_json,
                    data_json             = excluded.data_json
                """,
                (
                    str(package.id),
                    str(package.hypothesis_id),
                    package.retrieval_confidence,
                    json.dumps(package.sources_queried),
                    json.dumps(package.sources_failed),
                    package.sealed_at.isoformat(),
                    data_json,
                ),
            )
            conn.commit()
        logger.debug("retrieval_package_saved", extra={"package_id": str(package.id)})

    def get_retrieval_package(self, hypothesis_id: str) -> RetrievalPackage | None:
        """Retrieve the RetrievalPackage for a given hypothesis.

        Args:
            hypothesis_id: UUID string of the owning hypothesis.

        Returns:
            RetrievalPackage domain object, or None if not found.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json FROM retrieval_packages WHERE hypothesis_id = ?",
                (hypothesis_id,),
            ).fetchone()
        if row is None:
            return None
        return RetrievalPackage.model_validate_json(row["data_json"])

    # ─────────────────────────────────────────────
    # ReasoningResult
    # ─────────────────────────────────────────────

    def save_reasoning_result(self, result: ReasoningResult) -> None:
        """Persist a ReasoningResult record (upsert).

        Args:
            result: The ReasoningResult domain object to persist.
        """
        data_json = result.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reasoning_results
                    (id, hypothesis_id, recommendation_status,
                     support_score, mechanistic_score, risk_score,
                     rule_set_version, reasoning_duration_ms,
                     completed_at, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    recommendation_status  = excluded.recommendation_status,
                    support_score          = excluded.support_score,
                    mechanistic_score      = excluded.mechanistic_score,
                    risk_score             = excluded.risk_score,
                    reasoning_duration_ms  = excluded.reasoning_duration_ms,
                    data_json              = excluded.data_json
                """,
                (
                    str(result.id),
                    str(result.hypothesis_id),
                    result.recommendation_status.value,
                    result.support_assessment.score,
                    result.mechanistic_assessment.score,
                    result.risk_assessment.score,
                    result.rule_set_version,
                    result.reasoning_duration_ms,
                    result.completed_at.isoformat(),
                    data_json,
                ),
            )
            conn.commit()
        logger.debug("reasoning_result_saved", extra={"result_id": str(result.id)})

    def get_reasoning_result(self, hypothesis_id: str) -> ReasoningResult | None:
        """Retrieve the ReasoningResult for a given hypothesis.

        Args:
            hypothesis_id: UUID string of the hypothesis.

        Returns:
            ReasoningResult domain object, or None if not found.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json FROM reasoning_results WHERE hypothesis_id = ?",
                (hypothesis_id,),
            ).fetchone()
        if row is None:
            return None
        return ReasoningResult.model_validate_json(row["data_json"])

    # ─────────────────────────────────────────────
    # Evaluation History
    # ─────────────────────────────────────────────

    def list_evaluations(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return a list of evaluation summaries, most recent first.

        Joins hypotheses, reasoning results, and retrieval packages to
        provide a compact summary for the history page and API.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of dicts with evaluation summary fields.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    h.id          AS hypothesis_id,
                    h.drug_name,
                    h.disease_name,
                    h.lifecycle_state,
                    h.created_at,
                    rr.recommendation_status AS recommendation,
                    rr.support_score,
                    rr.mechanistic_score,
                    rr.risk_score,
                    rr.completed_at,
                    rp.retrieval_confidence,
                    rp.sources_queried_json
                FROM hypotheses h
                LEFT JOIN reasoning_results rr ON rr.hypothesis_id = h.id
                LEFT JOIN retrieval_packages rp ON rp.hypothesis_id = h.id
                ORDER BY h.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            sources_queried: list[str] = []
            if row["sources_queried_json"]:
                try:
                    sources_queried = json.loads(row["sources_queried_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append({
                "hypothesis_id": row["hypothesis_id"],
                "drug_name": row["drug_name"],
                "disease_name": row["disease_name"],
                "lifecycle_state": row["lifecycle_state"],
                "created_at": row["created_at"],
                "recommendation": row["recommendation"] or "PENDING",
                "support_score": row["support_score"] or 0.0,
                "mechanistic_score": row["mechanistic_score"] or 0.0,
                "risk_score": row["risk_score"] or 0.0,
                "completed_at": row["completed_at"],
                "retrieval_confidence": row["retrieval_confidence"] or "UNKNOWN",
                "sources_queried": sources_queried,
            })
        return result

    def delete_hypothesis(self, hypothesis_id: str) -> bool:
        """Delete all records for a hypothesis (cascade).

        Args:
            hypothesis_id: UUID string to delete.

        Returns:
            True if the hypothesis existed and was deleted.
        """
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM reasoning_results WHERE hypothesis_id = ?",
                (hypothesis_id,),
            )
            conn.execute(
                "DELETE FROM retrieval_packages WHERE hypothesis_id = ?",
                (hypothesis_id,),
            )
            result = conn.execute(
                "DELETE FROM hypotheses WHERE id = ?",
                (hypothesis_id,),
            )
            conn.commit()
        deleted = result.rowcount > 0
        if deleted:
            logger.info("hypothesis_deleted", extra={"hypothesis_id": hypothesis_id})
        return deleted
