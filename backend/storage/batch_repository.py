"""BatchRepository — SQLite persistence for batch evaluation jobs.

Phase 3 Production Feature: stores batch job state, item-level results,
and progress tracking for the batch evaluation API.

Reference: Phase 3 — Batch processing
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# DDL
# ─────────────────────────────────────────────

_DDL_BATCH_JOBS = """
CREATE TABLE IF NOT EXISTS batch_jobs (
    batch_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'PENDING',
    total_items INTEGER NOT NULL DEFAULT 0,
    completed_items INTEGER NOT NULL DEFAULT 0,
    failed_items INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
"""

_DDL_BATCH_ITEMS = """
CREATE TABLE IF NOT EXISTS batch_items (
    item_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    drug_name TEXT NOT NULL,
    disease_name TEXT NOT NULL,
    retrieval_policy TEXT NOT NULL DEFAULT 'STANDARD',
    status TEXT NOT NULL DEFAULT 'PENDING',
    hypothesis_id TEXT,
    recommendation TEXT,
    support_score REAL,
    mechanistic_score REAL,
    risk_score REAL,
    error_message TEXT,
    started_at TEXT,
    completed_at TEXT,
    result_json TEXT,
    FOREIGN KEY (batch_id) REFERENCES batch_jobs(batch_id)
);
"""

_DDL_BATCH_ITEMS_IDX = """
CREATE INDEX IF NOT EXISTS idx_batch_items_batch_id ON batch_items(batch_id);
CREATE INDEX IF NOT EXISTS idx_batch_items_status ON batch_items(status);
"""


class BatchRepository:
    """Repository for batch evaluation job persistence.

    Stores batch job state and per-item results in SQLite.
    Supports status polling, partial result retrieval, and progress tracking.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str = "data/cynthera.db") -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(_DDL_BATCH_JOBS)
            conn.execute(_DDL_BATCH_ITEMS)
            for stmt in _DDL_BATCH_ITEMS_IDX.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    try:
                        conn.execute(stmt)
                    except sqlite3.OperationalError:
                        pass
            conn.commit()

    # ─────────────────────────────────────────────
    # Batch Job Operations
    # ─────────────────────────────────────────────

    def create_batch(
        self,
        items: list[dict[str, str]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a new batch job with the given items.

        Args:
            items: List of dicts with 'drug_name', 'disease_name', optionally 'retrieval_policy'.
            metadata: Optional metadata dict to store with the job.

        Returns:
            The batch_id (UUID string).
        """
        batch_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO batch_jobs
                    (batch_id, status, total_items, completed_items, failed_items,
                     created_at, updated_at, metadata_json)
                VALUES (?, 'PENDING', ?, 0, 0, ?, ?, ?)
                """,
                (
                    batch_id,
                    len(items),
                    now,
                    now,
                    json.dumps(metadata or {}),
                ),
            )
            for item in items:
                item_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO batch_items
                        (item_id, batch_id, drug_name, disease_name, retrieval_policy, status)
                    VALUES (?, ?, ?, ?, ?, 'PENDING')
                    """,
                    (
                        item_id,
                        batch_id,
                        item["drug_name"],
                        item["disease_name"],
                        item.get("retrieval_policy", "STANDARD").upper(),
                    ),
                )
            conn.commit()

        logger.info(
            "batch_created",
            extra={"batch_id": batch_id, "item_count": len(items)},
        )
        return batch_id

    def get_batch_status(self, batch_id: str) -> dict[str, Any] | None:
        """Get the status and progress of a batch job.

        Returns:
            Dict with batch metadata and progress, or None if not found.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM batch_jobs WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()

        if row is None:
            return None

        return {
            "batch_id": row["batch_id"],
            "status": row["status"],
            "total_items": row["total_items"],
            "completed_items": row["completed_items"],
            "failed_items": row["failed_items"],
            "progress_pct": (
                round(row["completed_items"] / row["total_items"] * 100, 1)
                if row["total_items"] > 0 else 0.0
            ),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "completed_at": row["completed_at"],
        }

    def get_batch_items(
        self, batch_id: str, status_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Get all items in a batch, optionally filtered by status.

        Args:
            batch_id: Batch job ID.
            status_filter: Optional status ('PENDING', 'RUNNING', 'DONE', 'FAILED').

        Returns:
            List of item dicts.
        """
        with self._connect() as conn:
            if status_filter:
                rows = conn.execute(
                    "SELECT * FROM batch_items WHERE batch_id = ? AND status = ? ORDER BY rowid",
                    (batch_id, status_filter),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM batch_items WHERE batch_id = ? ORDER BY rowid",
                    (batch_id,),
                ).fetchall()

        return [
            {
                "item_id": r["item_id"],
                "drug_name": r["drug_name"],
                "disease_name": r["disease_name"],
                "retrieval_policy": r["retrieval_policy"],
                "status": r["status"],
                "hypothesis_id": r["hypothesis_id"],
                "recommendation": r["recommendation"],
                "support_score": r["support_score"],
                "mechanistic_score": r["mechanistic_score"],
                "risk_score": r["risk_score"],
                "error_message": r["error_message"],
                "started_at": r["started_at"],
                "completed_at": r["completed_at"],
            }
            for r in rows
        ]

    def get_pending_items(self, batch_id: str) -> list[dict[str, Any]]:
        """Get all PENDING items for a batch (for processing)."""
        return self.get_batch_items(batch_id, status_filter="PENDING")

    def mark_item_running(self, item_id: str) -> None:
        """Mark a batch item as running."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE batch_items SET status = 'RUNNING', started_at = ? WHERE item_id = ?",
                (now, item_id),
            )
            conn.commit()

    def mark_item_done(
        self,
        item_id: str,
        hypothesis_id: str,
        recommendation: str,
        support_score: float,
        mechanistic_score: float,
        risk_score: float,
        result_json: str,
    ) -> None:
        """Mark a batch item as completed with results."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE batch_items SET
                    status = 'DONE',
                    hypothesis_id = ?,
                    recommendation = ?,
                    support_score = ?,
                    mechanistic_score = ?,
                    risk_score = ?,
                    result_json = ?,
                    completed_at = ?
                WHERE item_id = ?
                """,
                (
                    hypothesis_id,
                    recommendation,
                    support_score,
                    mechanistic_score,
                    risk_score,
                    result_json,
                    now,
                    item_id,
                ),
            )
            # Increment completed count on parent job
            conn.execute(
                """
                UPDATE batch_jobs SET
                    completed_items = completed_items + 1,
                    updated_at = ?
                WHERE batch_id = (SELECT batch_id FROM batch_items WHERE item_id = ?)
                """,
                (now, item_id),
            )
            conn.commit()
        self._check_batch_completion(item_id)

    def mark_item_failed(self, item_id: str, error_message: str) -> None:
        """Mark a batch item as failed."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE batch_items SET
                    status = 'FAILED',
                    error_message = ?,
                    completed_at = ?
                WHERE item_id = ?
                """,
                (error_message[:500], now, item_id),
            )
            conn.execute(
                """
                UPDATE batch_jobs SET
                    failed_items = failed_items + 1,
                    completed_items = completed_items + 1,
                    updated_at = ?
                WHERE batch_id = (SELECT batch_id FROM batch_items WHERE item_id = ?)
                """,
                (now, item_id),
            )
            conn.commit()
        self._check_batch_completion(item_id)

    def _check_batch_completion(self, item_id: str) -> None:
        """Check if all items are done and update batch status accordingly."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT bj.batch_id, bj.total_items, bj.completed_items
                FROM batch_jobs bj
                JOIN batch_items bi ON bi.batch_id = bj.batch_id
                WHERE bi.item_id = ?
                """,
                (item_id,),
            ).fetchone()

            if row and row["completed_items"] >= row["total_items"]:
                conn.execute(
                    """
                    UPDATE batch_jobs SET
                        status = 'COMPLETED',
                        completed_at = ?
                    WHERE batch_id = ?
                    """,
                    (now, row["batch_id"]),
                )
                conn.commit()
                logger.info("batch_completed", extra={"batch_id": row["batch_id"]})

    def mark_batch_running(self, batch_id: str) -> None:
        """Mark a batch job as RUNNING."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE batch_jobs SET status = 'RUNNING', updated_at = ? WHERE batch_id = ?",
                (now, batch_id),
            )
            conn.commit()

    def list_batches(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent batch jobs."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM batch_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [
            {
                "batch_id": r["batch_id"],
                "status": r["status"],
                "total_items": r["total_items"],
                "completed_items": r["completed_items"],
                "failed_items": r["failed_items"],
                "created_at": r["created_at"],
                "completed_at": r["completed_at"],
            }
            for r in rows
        ]
