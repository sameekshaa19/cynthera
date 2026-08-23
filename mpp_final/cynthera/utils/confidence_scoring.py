"""
Confidence scoring and uncertainty quantification utilities.
Implements evidence strength calculation, source weighting, and confidence aggregation.
"""
from typing import List, Dict
from models.data_models import (
    Evidence,
    EvidenceSource,
    ConfidenceScore,
    ConfidenceLevel
)

# Source reliability weights (based on evidence hierarchy)
SOURCE_WEIGHTS = {
    EvidenceSource.EXPERIMENTAL: 1.0,  # Highest confidence
    EvidenceSource.CURATED: 0.8,
    EvidenceSource.CLINICAL: 0.7,
    EvidenceSource.LITERATURE: 0.6,
    EvidenceSource.PREDICTED: 0.4,  # Lowest confidence
}

# Database reliability scores
DATABASE_RELIABILITY = {
    'chembl': 0.9,
    'drugbank': 0.9,
    'pubchem': 0.85,
    'reactome': 0.85,
    'uniprot': 0.9,
    'pubmed': 0.7,  # Varies by article
    'disgenet': 0.75,
    'wikipathways': 0.7,
    'kegg': 0.8,
}


def calculate_evidence_strength(evidence: Evidence) -> float:
    """
    Calculate strength of a single piece of evidence.
    
    Args:
        evidence: Evidence object
    
    Returns:
        Strength score between 0 and 1
    """
    # Base score from evidence source type
    source_weight = SOURCE_WEIGHTS.get(evidence.source, 0.5)
    
    # Database reliability
    db_reliability = DATABASE_RELIABILITY.get(evidence.database.lower(), 0.5)
    
    # Evidence's own confidence
    evidence_confidence = evidence.confidence.value
    
    # Weighted combination
    strength = (
        source_weight * 0.4 +
        db_reliability * 0.3 +
        evidence_confidence * 0.3
    )
    
    return min(max(strength, 0.0), 1.0)


def aggregate_evidence_confidence(evidence_list: List[Evidence]) -> ConfidenceScore:
    """
    Aggregate confidence from multiple pieces of evidence.
    Uses weighted average with diminishing returns for redundant evidence.
    
    Args:
        evidence_list: List of Evidence objects
    
    Returns:
        Aggregated ConfidenceScore
    """
    if not evidence_list:
        return ConfidenceScore(
            value=0.0,
            level=ConfidenceLevel.UNKNOWN,
            rationale="No evidence available"
        )
    
    # Calculate individual strengths
    strengths = [calculate_evidence_strength(ev) for ev in evidence_list]
    
    # Group by source type to apply diminishing returns
    source_groups: Dict[EvidenceSource, List[float]] = {}
    for ev, strength in zip(evidence_list, strengths):
        if ev.source not in source_groups:
            source_groups[ev.source] = []
        source_groups[ev.source].append(strength)
    
    # Aggregate with diminishing returns per source type
    total_confidence = 0.0
    for source_type, source_strengths in source_groups.items():
        # Sort descending
        source_strengths.sort(reverse=True)
        
        # Apply diminishing returns: 1.0, 0.5, 0.33, 0.25, ...
        for i, strength in enumerate(source_strengths):
            weight = 1.0 / (i + 1)
            total_confidence += strength * weight
    
    # Normalize by number of source types (more diverse sources = higher confidence)
    num_source_types = len(source_groups)
    diversity_bonus = min(num_source_types / 4.0, 1.0)  # Max bonus at 4+ source types
    
    final_confidence = min(
        (total_confidence / max(len(evidence_list), 1)) * (1 + diversity_bonus * 0.2),
        1.0
    )
    
    # Generate rationale
    source_summary = ", ".join([
        f"{len(strengths)} {source.value}" 
        for source, strengths in source_groups.items()
    ])
    rationale = f"Based on {len(evidence_list)} evidence items ({source_summary})"
    
    return ConfidenceScore(
        value=final_confidence,
        level=ConfidenceLevel.HIGH,  # Will be auto-determined by validator
        rationale=rationale
    )


def combine_confidence_scores(
    scores: List[ConfidenceScore],
    method: str = "conservative"
) -> ConfidenceScore:
    """
    Combine multiple confidence scores.
    
    Args:
        scores: List of ConfidenceScore objects
        method: Combination method ('conservative', 'average', 'optimistic')
    
    Returns:
        Combined ConfidenceScore
    """
    if not scores:
        return ConfidenceScore(
            value=0.0,
            level=ConfidenceLevel.UNKNOWN,
            rationale="No confidence scores to combine"
        )
    
    values = [s.value for s in scores]
    
    if method == "conservative":
        # Use minimum (most conservative)
        combined_value = min(values)
        rationale = f"Conservative estimate from {len(scores)} scores (min: {combined_value:.2f})"
    
    elif method == "optimistic":
        # Use maximum (most optimistic)
        combined_value = max(values)
        rationale = f"Optimistic estimate from {len(scores)} scores (max: {combined_value:.2f})"
    
    else:  # average
        # Use weighted average
        combined_value = sum(values) / len(values)
        rationale = f"Average of {len(scores)} scores (mean: {combined_value:.2f})"
    
    return ConfidenceScore(
        value=combined_value,
        level=ConfidenceLevel.HIGH,  # Will be auto-determined
        rationale=rationale
    )


def penalize_for_conflicts(
    base_confidence: ConfidenceScore,
    num_conflicts: int
) -> ConfidenceScore:
    """
    Reduce confidence based on number of conflicts.
    
    Args:
        base_confidence: Base confidence score
        num_conflicts: Number of conflicting claims
    
    Returns:
        Adjusted ConfidenceScore
    """
    if num_conflicts == 0:
        return base_confidence
    
    # Penalty: -10% per conflict, max -50%
    penalty = min(num_conflicts * 0.1, 0.5)
    adjusted_value = max(base_confidence.value * (1 - penalty), 0.0)
    
    return ConfidenceScore(
        value=adjusted_value,
        level=ConfidenceLevel.HIGH,  # Will be auto-determined
        rationale=f"{base_confidence.rationale}. Reduced by {penalty*100:.0f}% due to {num_conflicts} conflict(s)"
    )


def calculate_pathway_relevance_score(
    pathway_genes: List[str],
    disease_genes: List[str],
    drug_targets: List[str]
) -> float:
    """
    Calculate pathway relevance based on gene overlap.
    
    Args:
        pathway_genes: Genes in the pathway
        disease_genes: Disease-associated genes
        drug_targets: Drug target genes
    
    Returns:
        Relevance score between 0 and 1
    """
    if not pathway_genes:
        return 0.0
    
    # Convert to sets for intersection
    pathway_set = set(g.upper() for g in pathway_genes)
    disease_set = set(g.upper() for g in disease_genes)
    target_set = set(g.upper() for g in drug_targets)
    
    # Calculate overlaps
    disease_overlap = len(pathway_set & disease_set) / len(pathway_set) if pathway_set else 0
    target_overlap = len(pathway_set & target_set) / len(pathway_set) if pathway_set else 0
    
    # Both overlaps are important
    # Disease overlap: pathway is relevant to disease
    # Target overlap: drug affects the pathway
    relevance = (disease_overlap * 0.6 + target_overlap * 0.4)
    
    return min(max(relevance, 0.0), 1.0)


def determine_confidence_level_from_value(value: float) -> ConfidenceLevel:
    """
    Determine categorical confidence level from numeric value.
    
    Args:
        value: Confidence value between 0 and 1
    
    Returns:
        ConfidenceLevel enum
    """
    if value >= 0.75:
        return ConfidenceLevel.HIGH
    elif value >= 0.50:
        return ConfidenceLevel.MEDIUM
    elif value >= 0.25:
        return ConfidenceLevel.LOW
    else:
        return ConfidenceLevel.UNKNOWN
