"""Batch Evaluation API Routes — Phase 3 Production Feature.

Endpoints:
    POST /api/v1/batch/evaluate     — Submit a batch of drug-disease pairs
    GET  /api/v1/batch/{batch_id}   — Get batch status and progress
    GET  /api/v1/batch/{batch_id}/results — Get all completed item results
    GET  /api/v1/batch             — List recent batches

Reference: Phase 3 — Batch processing, 07_API_CONTRACTS.md
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.storage.batch_repository import BatchRepository

load_dotenv()

logger = logging.getLogger(__name__)

batch_router = APIRouter(prefix="/api/v1/batch", tags=["Batch Evaluation"])

_DB_PATH = "data/cynthera.db"
_batch_repo = BatchRepository(db_path=_DB_PATH)


# ─────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────

class BatchItem(BaseModel):
    """A single drug-disease pair in a batch request."""
    drug_name: str = Field(..., min_length=1, max_length=200)
    disease_name: str = Field(..., min_length=1, max_length=200)
    retrieval_policy: str = Field(
        default="STANDARD",
        pattern="^(STANDARD|FAST|COMPREHENSIVE)$",
    )


class BatchEvaluationRequest(BaseModel):
    """Request body for POST /api/v1/batch/evaluate."""
    items: list[BatchItem] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="List of drug-disease pairs to evaluate (max 50).",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Optional metadata to attach to the batch job.",
    )


class BatchSubmitResponse(BaseModel):
    """Response returned immediately after batch submission."""
    batch_id: str
    total_items: int
    status: str
    message: str


class BatchStatusResponse(BaseModel):
    """Batch job status response."""
    batch_id: str
    status: str
    total_items: int
    completed_items: int
    failed_items: int
    progress_pct: float
    created_at: str
    updated_at: str
    completed_at: str | None


# ─────────────────────────────────────────────
# Background Task
# ─────────────────────────────────────────────

async def _process_batch(batch_id: str, items: list[BatchItem]) -> None:
    """Background task: process all batch items concurrently.

    Each item is evaluated via the MasterOrchestrator. Items that fail are
    marked FAILED with the error message; successful items are marked DONE.

    Runs at most 5 concurrent evaluations to avoid resource exhaustion.
    """
    _batch_repo.mark_batch_running(batch_id)

    # Get item IDs from repo
    pending = _batch_repo.get_pending_items(batch_id)
    if not pending:
        return

    # Build a semaphore-guarded processing coroutine
    semaphore = asyncio.Semaphore(5)  # max 5 concurrent evaluations

    policy_map = {
        "STANDARD": RetrievalPolicy.STANDARD,
        "FAST": RetrievalPolicy.FAST,
        "COMPREHENSIVE": RetrievalPolicy.COMPREHENSIVE,
    }

    async def _evaluate_item(item_data: dict[str, Any]) -> None:
        async with semaphore:
            item_id = item_data["item_id"]
            _batch_repo.mark_item_running(item_id)

            try:
                orchestrator = MasterOrchestrator(
                    llm_api_key=os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY"),
                    ncbi_api_key=os.environ.get("NCBI_API_KEY"),
                    disgenet_api_key=os.environ.get("DISGENET_API_KEY"),
                    db_path=_DB_PATH,
                )
                policy = policy_map.get(item_data["retrieval_policy"], RetrievalPolicy.STANDARD)

                hypothesis, package, result = await orchestrator.evaluate(
                    drug_name=item_data["drug_name"],
                    disease_name=item_data["disease_name"],
                    policy=policy,
                )

                _batch_repo.mark_item_done(
                    item_id=item_id,
                    hypothesis_id=str(hypothesis.id),
                    recommendation=result.recommendation_status.value,
                    support_score=result.support_assessment.score,
                    mechanistic_score=result.mechanistic_assessment.score,
                    risk_score=result.risk_assessment.score,
                    result_json=result.model_dump_json(),
                )

                logger.info(
                    "batch_item_completed",
                    extra={
                        "batch_id": batch_id,
                        "item_id": item_id,
                        "drug": item_data["drug_name"],
                        "disease": item_data["disease_name"],
                    },
                )

            except Exception as exc:
                _batch_repo.mark_item_failed(item_id, str(exc)[:400])
                logger.error(
                    "batch_item_failed",
                    extra={
                        "batch_id": batch_id,
                        "item_id": item_id,
                        "error": str(exc),
                    },
                )

    # Run all items concurrently (semaphore-bounded)
    tasks = [_evaluate_item(item) for item in pending]
    await asyncio.gather(*tasks, return_exceptions=True)

    logger.info("batch_processing_complete", extra={"batch_id": batch_id})


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@batch_router.post("/evaluate", response_model=BatchSubmitResponse, status_code=202)
async def submit_batch(
    request: BatchEvaluationRequest,
    background_tasks: BackgroundTasks,
) -> BatchSubmitResponse:
    """Submit a batch of drug-disease pairs for evaluation.

    Processing happens asynchronously in the background. Poll
    GET /api/v1/batch/{batch_id} for progress.

    Args:
        request: Batch evaluation request with up to 50 items.

    Returns:
        BatchSubmitResponse with batch_id for status polling.
    """
    item_dicts = [item.model_dump() for item in request.items]
    batch_id = _batch_repo.create_batch(
        items=item_dicts,
        metadata=request.metadata,
    )

    # Schedule background processing
    background_tasks.add_task(
        asyncio.ensure_future,
        _process_batch(batch_id, request.items),
    )

    logger.info(
        "batch_submitted",
        extra={"batch_id": batch_id, "item_count": len(request.items)},
    )

    return BatchSubmitResponse(
        batch_id=batch_id,
        total_items=len(request.items),
        status="PENDING",
        message=(
            f"Batch job {batch_id} submitted with {len(request.items)} item(s). "
            f"Poll GET /api/v1/batch/{batch_id} for progress."
        ),
    )


@batch_router.get("/{batch_id}", response_model=BatchStatusResponse)
async def get_batch_status(batch_id: str) -> BatchStatusResponse:
    """Get the status and progress of a batch job.

    Args:
        batch_id: UUID of the batch job.

    Returns:
        BatchStatusResponse with progress metrics.

    Raises:
        404: If batch_id is not found.
    """
    status = _batch_repo.get_batch_status(batch_id)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail=f"Batch job '{batch_id}' not found.",
        )
    return BatchStatusResponse(**status)


@batch_router.get("/{batch_id}/results")
async def get_batch_results(batch_id: str) -> dict[str, Any]:
    """Get all item results for a completed (or in-progress) batch.

    Args:
        batch_id: UUID of the batch job.

    Returns:
        Dict with batch status and list of item results.

    Raises:
        404: If batch_id is not found.
    """
    status = _batch_repo.get_batch_status(batch_id)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail=f"Batch job '{batch_id}' not found.",
        )

    items = _batch_repo.get_batch_items(batch_id)
    return {
        "batch_id": batch_id,
        "status": status["status"],
        "progress_pct": status["progress_pct"],
        "items": items,
    }


@batch_router.get("")
async def list_batches(limit: int = 20) -> list[dict[str, Any]]:
    """List recent batch jobs.

    Args:
        limit: Maximum number of batches to return (default 20, max 100).

    Returns:
        List of batch job summaries.
    """
    return _batch_repo.list_batches(limit=min(limit, 100))
