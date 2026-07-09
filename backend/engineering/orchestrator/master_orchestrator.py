"""MasterOrchestrator — top-level coordinator of the CYNTHERA pipeline.

Reference: 01_SYSTEM_ARCHITECTURE.md §3.3, 08_IMPLEMENTATION_GUIDE.md
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from backend.core.domain.hypothesis import Hypothesis
from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.domain.reasoning_result import ReasoningResult
from backend.core.enums.lifecycle import HypothesisLifecycleState
from backend.core.enums.retrieval_policy import RetrievalPolicy
from backend.core.exceptions import (
    DrugNotResolvedException,
    DiseaseNotResolvedException,
    QualityGateFailureError,
)
from backend.engineering.identity.resolution_service import IdentifierResolutionService
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator

logger = logging.getLogger(__name__)


class MasterOrchestrator:
    """Top-level coordinator that manages the 10-step evaluation pipeline.

    Coordinates:
    1. Input validation
    2. Identifier resolution
    3. Parallel data retrieval
    4. Data normalization (within retrieval pipeline)
    5. Canonical domain model creation
    6. Claim extraction (delegated to ReasoningOrchestrator)
    7. Contradiction detection
    8. 3D score computation
    9. Recommendation rules
    10. Report assembly

    Raises:
        DrugNotResolvedException: If drug name cannot be mapped to a standard ID.
        DiseaseNotResolvedException: If disease name cannot be mapped.
        QualityGateFailureError: If retrieved data fails quality checks.
    """

    def __init__(
        self,
        ncbi_api_key: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str = "gemini-1.5-flash",
    ) -> None:
        """Initialize the MasterOrchestrator with all subsystem components.

        Args:
            ncbi_api_key: Optional NCBI API key for higher PubMed rate limits.
            llm_api_key: LLM API key for claim extraction.
            llm_model: LLM model name (default 'gemini-1.5-flash').
        """
        self._resolver = IdentifierResolutionService(ncbi_api_key=ncbi_api_key)
        self._retrieval = RetrievalPipeline(ncbi_api_key=ncbi_api_key)
        self._reasoning = ReasoningOrchestrator(
            llm_api_key=llm_api_key,
            llm_model=llm_model,
        )

    async def evaluate(
        self,
        drug_name: str,
        disease_name: str,
        policy: RetrievalPolicy = RetrievalPolicy.STANDARD,
        trace_id: uuid.UUID | None = None,
    ) -> tuple[Hypothesis, RetrievalPackage, ReasoningResult]:
        """Execute the full 10-step CYNTHERA evaluation pipeline.

        Args:
            drug_name: Drug common name (e.g., 'Sildenafil').
            disease_name: Disease common name (e.g., 'Pulmonary Arterial Hypertension').
            policy: RetrievalPolicy controlling depth of data retrieval.
            trace_id: Optional trace ID for log correlation.

        Returns:
            Tuple of (Hypothesis, RetrievalPackage, ReasoningResult).

        Raises:
            DrugNotResolvedException: If the drug cannot be resolved.
            DiseaseNotResolvedException: If the disease cannot be resolved.
        """
        if trace_id is None:
            trace_id = uuid.uuid4()

        logger.info(
            "evaluation_start",
            extra={
                "drug": drug_name,
                "disease": disease_name,
                "policy": policy.value,
                "trace_id": str(trace_id),
            },
        )

        # Step 1: Initialize Hypothesis
        hypothesis = Hypothesis(
            drug_name=drug_name,
            disease_name=disease_name,
            retrieval_policy=policy,
            trace_id=trace_id,
        )

        try:
            # Step 2: Identifier Resolution
            logger.info("step_id_resolution", extra={"trace_id": str(trace_id)})
            drug_ids, disease_ids = await asyncio.gather(
                self._resolver.resolve_drug(drug_name, trace_id),
                self._resolver.resolve_disease(disease_name, trace_id),
            )

            drug = Drug(name=drug_name, identifiers=drug_ids)
            disease = Disease(name=disease_name, identifiers=disease_ids)

            hypothesis.transition_to(HypothesisLifecycleState.ID_RESOLVED)

            # Step 3: Parallel Data Retrieval
            logger.info("step_retrieval", extra={"trace_id": str(trace_id)})
            package = await self._retrieval.execute(drug, disease, hypothesis.id)
            hypothesis.transition_to(HypothesisLifecycleState.DATA_RETRIEVED)

            # Step 4–5: Normalization is embedded in the retrieval pipeline
            hypothesis.transition_to(HypothesisLifecycleState.NORMALIZED)

            # Steps 6–9: Full reasoning pipeline
            logger.info("step_reasoning", extra={"trace_id": str(trace_id)})
            result = await self._reasoning.reason(package)
            hypothesis.transition_to(HypothesisLifecycleState.EVALUATED)

            hypothesis.transition_to(HypothesisLifecycleState.COMPLETED)

            logger.info(
                "evaluation_complete",
                extra={
                    "trace_id": str(trace_id),
                    "recommendation": result.recommendation_status.value,
                    "duration_ms": result.reasoning_duration_ms,
                },
            )
            return hypothesis, package, result

        except (DrugNotResolvedException, DiseaseNotResolvedException) as exc:
            hypothesis.transition_to(HypothesisLifecycleState.FAILED, error=str(exc))
            logger.error(
                "entity_resolution_failed",
                extra={"trace_id": str(trace_id), "error": str(exc)},
            )
            raise

        except Exception as exc:
            hypothesis.transition_to(HypothesisLifecycleState.FAILED, error=str(exc))
            logger.critical(
                "evaluation_failed",
                extra={"trace_id": str(trace_id), "error": str(exc)},
                exc_info=True,
            )
            raise
