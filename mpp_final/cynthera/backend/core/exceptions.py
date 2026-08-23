"""Domain-level exception types for CYNTHERA.

Reference: 08_IMPLEMENTATION_GUIDE.md §4.5
"""
from __future__ import annotations

import uuid


class CyntheraBaseException(Exception):
    """Base class for all CYNTHERA domain exceptions.

    All exceptions carry: message, context dict, optional cause, trace_id.
    """

    def __init__(
        self,
        message: str,
        context: dict | None = None,
        trace_id: str | uuid.UUID | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict = context or {}
        self.trace_id = str(trace_id) if trace_id else None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, context={self.context})"


# ─────────────────────────────────────────────
# Identity Resolution Exceptions
# ─────────────────────────────────────────────


class EntityResolutionError(CyntheraBaseException):
    """Raised when an entity (drug or disease) cannot be resolved to a standard identifier."""


class DrugNotResolvedException(EntityResolutionError):
    """Raised when the drug name cannot be mapped to a ChEMBL/PubChem/DrugBank ID."""

    def __init__(
        self,
        drug_name: str,
        attempted_sources: list[str],
        trace_id: str | uuid.UUID | None = None,
    ) -> None:
        super().__init__(
            message=f"Drug '{drug_name}' could not be resolved to a standard identifier.",
            context={"drug_name": drug_name, "attempted_sources": attempted_sources},
            trace_id=trace_id,
        )
        self.drug_name = drug_name
        self.attempted_sources = attempted_sources


class DiseaseNotResolvedException(EntityResolutionError):
    """Raised when the disease name cannot be mapped to a MeSH/UMLS ID."""

    def __init__(
        self,
        disease_name: str,
        attempted_sources: list[str],
        trace_id: str | uuid.UUID | None = None,
    ) -> None:
        super().__init__(
            message=f"Disease '{disease_name}' could not be resolved to a standard identifier.",
            context={"disease_name": disease_name, "attempted_sources": attempted_sources},
            trace_id=trace_id,
        )
        self.disease_name = disease_name
        self.attempted_sources = attempted_sources


# ─────────────────────────────────────────────
# Retrieval Exceptions
# ─────────────────────────────────────────────


class SourceUnavailableError(CyntheraBaseException):
    """Raised when a critical data source is unreachable after all retries."""

    def __init__(
        self,
        source_name: str,
        retry_count: int,
        trace_id: str | uuid.UUID | None = None,
    ) -> None:
        super().__init__(
            message=f"Source '{source_name}' is unavailable after {retry_count} retries.",
            context={"source_name": source_name, "retry_count": retry_count},
            trace_id=trace_id,
        )
        self.source_name = source_name
        self.retry_count = retry_count


class QualityGateFailureError(CyntheraBaseException):
    """Raised when the RetrievalPackage fails the Quality Gate."""

    def __init__(
        self,
        failed_checks: list[str],
        trace_id: str | uuid.UUID | None = None,
    ) -> None:
        super().__init__(
            message=f"Quality Gate failed: {len(failed_checks)} check(s) did not pass.",
            context={"failed_checks": failed_checks},
            trace_id=trace_id,
        )
        self.failed_checks = failed_checks


# ─────────────────────────────────────────────
# Claim and Graph Exceptions
# ─────────────────────────────────────────────


class ClaimValidationError(CyntheraBaseException):
    """Raised when an unexpected structural error occurs during claim validation."""


class SealedGraphMutationError(CyntheraBaseException):
    """Raised when mutation is attempted on a sealed ClaimGraph."""

    def __init__(
        self,
        graph_id: str,
        operation: str,
        trace_id: str | uuid.UUID | None = None,
    ) -> None:
        super().__init__(
            message=f"Cannot perform '{operation}' on sealed ClaimGraph '{graph_id}'.",
            context={"graph_id": graph_id, "operation": operation},
            trace_id=trace_id,
        )
        self.graph_id = graph_id
        self.operation = operation


# ─────────────────────────────────────────────
# Infrastructure Exceptions
# ─────────────────────────────────────────────


class LLMResponseParsingError(CyntheraBaseException):
    """Raised when LLM output does not conform to the required JSON schema."""


class ConfigurationError(CyntheraBaseException):
    """Raised when the system configuration is invalid or missing required values."""


class ImmutableObjectError(CyntheraBaseException):
    """Raised when mutation is attempted on an immutable domain entity."""
