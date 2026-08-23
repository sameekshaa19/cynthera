"""MasterOrchestrator — top-level coordinator of the CYNTHERA pipeline.

Phase 3 enhanced with:
- EvaluationCache: returns cached results for identical drug-disease-policy combos
- KnowledgeStore shared instance passed to ReasoningOrchestrator

Reference: 01_SYSTEM_ARCHITECTURE.md §3.3, 08_IMPLEMENTATION_GUIDE.md
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid

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
from backend.core.utils.api_keys import sanitize_api_key
from backend.engineering.identity.resolution_service import IdentifierResolutionService
from backend.engineering.retrieval.pipeline import RetrievalPipeline
from backend.reasoning.orchestrator.reasoning_orchestrator import ReasoningOrchestrator
from backend.storage.repository import StorageRepository
from backend.infrastructure.cache.evaluation_cache import EvaluationCache

logger = logging.getLogger(__name__)


class MasterOrchestrator:
    """Top-level coordinator that manages the 10-step evaluation pipeline.

    Phase 3 enhancements:
    - Result caching: identical evaluations return cached results instantly
    - KnowledgeStore shared through to ReasoningOrchestrator

    Coordinates:
    1. Cache lookup
    2. Input validation
    3. Identifier resolution
    4. Parallel data retrieval
    5. Data normalization (within retrieval pipeline)
    6. Canonical domain model creation
    7. Claim extraction (delegated to ReasoningOrchestrator)
    8. Contradiction detection
    9. 3D score computation
    10. Recommendation rules
    11. Report assembly
    12. Cache storage

    Raises:
        DrugNotResolvedException: If drug name cannot be mapped to a standard ID.
        DiseaseNotResolvedException: If disease name cannot be mapped.
        QualityGateFailureError: If retrieved data fails quality checks.
    """

    def __init__(
        self,
        ncbi_api_key: str | None = None,
        disgenet_api_key: str | None = None,
        semantic_scholar_api_key: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str = "gemini-2.0-flash",
        db_path: str = "data/cynthera.db",
        cache_ttl_seconds: int = 86400,
        use_cache: bool = True,
    ) -> None:
        """Initialize the MasterOrchestrator with all subsystem components.

        Args:
            ncbi_api_key: Optional NCBI API key for higher PubMed rate limits.
            disgenet_api_key: Optional DisGeNET API key for gene-disease associations.
            semantic_scholar_api_key: Optional Semantic Scholar API key.
            llm_api_key: LLM API key for claim extraction.
            llm_model: LLM model name (default 'gemini-1.5-flash').
            db_path: Path to SQLite database file.
            cache_ttl_seconds: Cache TTL in seconds (default 86400 = 24h).
            use_cache: Whether to use the evaluation cache (default True).
        """
        self._db_path = db_path
        clean_ncbi = sanitize_api_key(ncbi_api_key)
        clean_disgenet = sanitize_api_key(disgenet_api_key)
        clean_s2 = sanitize_api_key(semantic_scholar_api_key)
        self._resolver = IdentifierResolutionService(ncbi_api_key=clean_ncbi)
        self._retrieval = RetrievalPipeline(
            ncbi_api_key=clean_ncbi,
            disgenet_api_key=clean_disgenet,
            semantic_scholar_api_key=clean_s2,
            db_path=db_path,
            bypass_raw_cache=not use_cache,
        )
        resolved_llm_key = (
            sanitize_api_key(llm_api_key)
            or sanitize_api_key(os.environ.get("GROQ_API_KEY"))
            or sanitize_api_key(os.environ.get("LLM_API_KEY"))
            or sanitize_api_key(os.environ.get("GEMINI_API_KEY"))
        )
        self._reasoning = ReasoningOrchestrator(
            llm_api_key=resolved_llm_key,
            llm_model=llm_model,
            db_path=db_path,
        )
        self._storage = StorageRepository(db_path=db_path)
        self._cache = EvaluationCache(db_path=db_path, ttl_seconds=cache_ttl_seconds)
        self._use_cache = use_cache

    async def evaluate(
        self,
        drug_name: str,
        disease_name: str,
        policy: RetrievalPolicy = RetrievalPolicy.STANDARD,
        trace_id: uuid.UUID | None = None,
        bypass_cache: bool = False,
    ) -> tuple[Hypothesis, RetrievalPackage, ReasoningResult]:
        """Execute the full CYNTHERA evaluation pipeline.

        Args:
            drug_name: Drug common name (e.g., 'Sildenafil').
            disease_name: Disease common name (e.g., 'Pulmonary Arterial Hypertension').
            policy: RetrievalPolicy controlling depth of data retrieval.
            trace_id: Optional trace ID for log correlation.
            bypass_cache: If True, skip cache lookup (force re-evaluation).

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

        # ── Step 1: Cache lookup ──────────────────────────────────────────
        if self._use_cache and not bypass_cache:
            cached_result = self._cache.get(drug_name, disease_name, policy.value)
            if cached_result is not None:
                logger.info(
                    "evaluation_cache_hit",
                    extra={
                        "drug": drug_name,
                        "disease": disease_name,
                        "hypothesis_id": str(cached_result.hypothesis_id),
                    },
                )
                # Reconstruct a minimal Hypothesis and empty package for the cached result
                hypothesis = Hypothesis(
                    drug_name=drug_name,
                    disease_name=disease_name,
                    retrieval_policy=policy,
                    trace_id=trace_id,
                )
                # Override with cached hypothesis ID
                hypothesis = hypothesis.model_copy(
                    update={"id": cached_result.hypothesis_id}
                )
                # Return minimal package — not re-retrieved
                package = self._storage.get_retrieval_package(
                    str(cached_result.hypothesis_id)
                )
                if package is None:
                    # Cache hit but no package — proceed normally
                    logger.info(
                        "cache_hit_no_package",
                        extra={"hypothesis_id": str(cached_result.hypothesis_id)},
                    )
                else:
                    hypothesis = hypothesis.model_copy(
                        update={
                            "drug_chembl_id": package.drug.chembl_id,
                            "disease_mesh_id": package.disease.mesh_id,
                        }
                    )
                    return hypothesis, package, cached_result

        # ── Step 2: Initialize Hypothesis ────────────────────────────────
        hypothesis = Hypothesis(
            drug_name=drug_name,
            disease_name=disease_name,
            retrieval_policy=policy,
            trace_id=trace_id,
        )

        try:
            # ── Step 3: Identifier Resolution ────────────────────────────
            logger.info("step_id_resolution", extra={"trace_id": str(trace_id)})
            drug_ids, disease_ids = await asyncio.gather(
                self._resolver.resolve_drug(drug_name, trace_id),
                self._resolver.resolve_disease(disease_name, trace_id),
            )

            drug = Drug(name=drug_name, identifiers=drug_ids)
            disease = Disease(name=disease_name, identifiers=disease_ids)

            hypothesis = hypothesis.model_copy(
                update={
                    "drug_chembl_id": drug.chembl_id,
                    "disease_mesh_id": disease.mesh_id,
                }
            )
            hypothesis.transition_to(HypothesisLifecycleState.ID_RESOLVED)
            self._storage.save_hypothesis(hypothesis)

            # Hard gate: If both drug (ChEMBL) and disease (MeSH/MONDO) failed resolution completely,
            # return RESOLUTION_FAILED immediately instead of running retrieval and downstream reasoning.
            if drug.chembl_id is None and disease.mesh_id is None and disease.mondo_id is None:
                logger.warning(
                    "resolution_failed_hard_gate_triggered",
                    extra={"drug": drug_name, "disease": disease_name},
                )
                res_failed = ReasoningResult.resolution_failed(
                    hypothesis.id, drug_name, disease_name
                )
                hypothesis.transition_to(HypothesisLifecycleState.EVALUATED)
                hypothesis.transition_to(HypothesisLifecycleState.COMPLETED)
                self._storage.save_hypothesis(hypothesis)
                self._storage.save_reasoning_result(res_failed)

                empty_package = RetrievalPackage(
                    hypothesis_id=hypothesis.id,
                    drug=drug,
                    disease=disease,
                    retrieval_confidence="LOW",
                    sources_failed=["chembl", "mesh", "opentargets"],
                )
                return hypothesis, empty_package, res_failed

            # ── Step 4: Parallel Data Retrieval ──────────────────────────
            logger.info("step_retrieval", extra={"trace_id": str(trace_id)})
            self._retrieval._bypass_raw_cache = bypass_cache or (not self._use_cache)
            package = await self._retrieval.execute(drug, disease, hypothesis.id)
            hypothesis.transition_to(HypothesisLifecycleState.DATA_RETRIEVED)
            self._storage.save_hypothesis(hypothesis)
            self._storage.save_retrieval_package(package)

            # ── Step 5–6: Normalization embedded in retrieval pipeline ────
            hypothesis.transition_to(HypothesisLifecycleState.NORMALIZED)

            # ── Steps 7–11: Full reasoning pipeline ──────────────────────
            logger.info("step_reasoning", extra={"trace_id": str(trace_id)})
            result = await self._reasoning.reason(package)
            hypothesis.transition_to(HypothesisLifecycleState.EVALUATED)
            self._storage.save_reasoning_result(result)

            hypothesis.transition_to(HypothesisLifecycleState.COMPLETED)
            self._storage.save_hypothesis(hypothesis)

            # ── Step 12: Cache the result ─────────────────────────────────
            if self._use_cache:
                self._cache.set(drug_name, disease_name, result, policy.value)

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
