"""PDF Report API Route — Phase 3 Production Feature.

Endpoint:
    GET /api/v1/report/{hypothesis_id}  — Download PDF report for a hypothesis

Reference: Phase 3 — Export to PDF reports
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.storage.repository import StorageRepository
from backend.reporting.pdf_exporter import PDFReporter

logger = logging.getLogger(__name__)

report_router = APIRouter(prefix="/api/v1", tags=["Reports"])

_DB_PATH = "data/cynthera.db"
_storage = StorageRepository(db_path=_DB_PATH)


@report_router.get("/report/{hypothesis_id}")
async def download_report(hypothesis_id: str) -> Response:
    """Download a PDF report for a completed hypothesis evaluation.

    Args:
        hypothesis_id: UUID of the hypothesis to report on.

    Returns:
        PDF file as binary response with appropriate content-type header.

    Raises:
        404: If no result found for the hypothesis ID.
        500: If PDF generation fails.
    """
    # Fetch hypothesis metadata
    hypothesis = _storage.get_hypothesis(hypothesis_id)
    result = _storage.get_reasoning_result(hypothesis_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No reasoning result found for hypothesis '{hypothesis_id}'.",
        )

    drug_name = hypothesis.drug_name if hypothesis else "Unknown Drug"
    disease_name = hypothesis.disease_name if hypothesis else "Unknown Disease"

    reporter = PDFReporter(drug_name=drug_name, disease_name=disease_name)

    try:
        pdf_bytes = reporter.generate(result)
    except Exception as exc:
        logger.error("report_generation_failed", extra={"error": str(exc)}, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed: {exc}",
        )

    # Determine content type
    is_pdf = pdf_bytes[:4] == b"%PDF"
    content_type = "application/pdf" if is_pdf else "text/plain; charset=utf-8"
    extension = "pdf" if is_pdf else "txt"

    safe_drug = drug_name.replace(" ", "_")[:30]
    safe_disease = disease_name.replace(" ", "_")[:30]
    filename = f"CYNTHERA_{safe_drug}_{safe_disease}_{hypothesis_id[:8]}.{extension}"

    logger.info(
        "report_generated",
        extra={
            "hypothesis_id": hypothesis_id,
            "size_bytes": len(pdf_bytes),
            "format": extension,
        },
    )

    return Response(
        content=pdf_bytes,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
