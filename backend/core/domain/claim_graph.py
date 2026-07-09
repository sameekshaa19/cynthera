"""ClaimGraph and ClaimRelation entities — relational graph of claims.

Reference: 02_DOMAIN_MODEL.md, 04_REASONING_SPECIFICATION.md
"""
from __future__ import annotations

import uuid
from pydantic import BaseModel, Field

from backend.core.domain.claim import Claim
from backend.core.enums.predicate_type import PredicateType


class ClaimRelation(BaseModel):
    """A directed edge in the ClaimGraph connecting two Claims.

    Attributes:
        id: Internal UUID.
        source_claim_id: UUID of the source Claim node.
        target_claim_id: UUID of the target Claim node.
        relation_type: PredicateType describing the edge relationship.
        weight: Numeric strength of this relation [0.0, 1.0].
    """

    model_config = {"frozen": True}

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source_claim_id: uuid.UUID = Field(..., description="UUID of the source Claim.")
    target_claim_id: uuid.UUID = Field(..., description="UUID of the target Claim.")
    relation_type: PredicateType = Field(..., description="Edge relationship type.")
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Relation strength.")


class ClaimGraph(BaseModel):
    """Directed graph of Claim nodes connected by ClaimRelations.

    Once sealed (is_sealed=True), the graph is immutable. Any mutation
    attempt after sealing must raise a SealedGraphMutationError.

    Attributes:
        id: Internal UUID of this ClaimGraph.
        hypothesis_id: UUID of the owning Hypothesis.
        claims: Dict of claim_id -> Claim for O(1) lookup.
        relations: List of directed edges between claims.
        is_sealed: If True, the graph is immutable.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Graph unique identifier.")
    hypothesis_id: uuid.UUID = Field(..., description="UUID of the owning Hypothesis.")
    claims: dict[str, Claim] = Field(
        default_factory=dict,
        description="Claim nodes keyed by string UUID.",
    )
    relations: list[ClaimRelation] = Field(
        default_factory=list,
        description="Directed edges between claims.",
    )
    is_sealed: bool = Field(default=False, description="If True, graph is immutable.")

    def add_claim(self, claim: Claim) -> None:
        """Add a Claim node to the graph.

        Args:
            claim: The Claim to add.

        Raises:
            SealedGraphMutationError: If the graph has been sealed.
        """
        from backend.core.exceptions import SealedGraphMutationError

        if self.is_sealed:
            raise SealedGraphMutationError(
                graph_id=str(self.id),
                operation="add_claim",
            )
        self.claims[str(claim.id)] = claim

    def add_relation(self, relation: ClaimRelation) -> None:
        """Add a ClaimRelation edge to the graph.

        Args:
            relation: The ClaimRelation edge to add.

        Raises:
            SealedGraphMutationError: If the graph has been sealed.
        """
        from backend.core.exceptions import SealedGraphMutationError

        if self.is_sealed:
            raise SealedGraphMutationError(
                graph_id=str(self.id),
                operation="add_relation",
            )
        self.relations.append(relation)

    def seal(self) -> None:
        """Seal this graph, making it immutable.

        Once sealed, add_claim and add_relation will raise SealedGraphMutationError.
        """
        object.__setattr__(self, "is_sealed", True)

    def get_claim(self, claim_id: uuid.UUID) -> Claim | None:
        """Retrieve a claim by UUID.

        Args:
            claim_id: UUID of the claim to retrieve.

        Returns:
            The Claim object, or None if not found.
        """
        return self.claims.get(str(claim_id))

    @property
    def node_count(self) -> int:
        """Total number of Claim nodes in the graph."""
        return len(self.claims)

    @property
    def edge_count(self) -> int:
        """Total number of ClaimRelation edges in the graph."""
        return len(self.relations)
