"""RetrievalPolicy enum — controls depth and scope of retrieval.

Reference: 03_RETRIEVAL_SPECIFICATION.md
"""
from enum import Enum


class RetrievalPolicy(str, Enum):
    """Controls the depth and scope of evidence retrieval."""

    STANDARD = "STANDARD"
    """Default retrieval: all seven sources, full parallel pipeline."""

    FAST = "FAST"
    """Reduced retrieval: ChEMBL + UniProt only, no literature."""

    COMPREHENSIVE = "COMPREHENSIVE"
    """Extended retrieval: all sources with higher record limits."""
