"""
Data models and schemas for the Cynthera drug repurposing system.
Uses Pydantic for validation and structured data representation.
"""
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, validator
from datetime import datetime
from enum import Enum


class ConfidenceLevel(str, Enum):
    """Confidence level enumeration."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class EvidenceSource(str, Enum):
    """Evidence source types."""
    EXPERIMENTAL = "experimental"
    CURATED = "curated"
    PREDICTED = "predicted"
    LITERATURE = "literature"
    CLINICAL = "clinical"


class ConfidenceScore(BaseModel):
    """Uncertainty quantification model."""
    value: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0 and 1")
    level: ConfidenceLevel = Field(..., description="Categorical confidence level")
    rationale: str = Field(..., description="Explanation for the confidence score")
    
    @validator('level', pre=True, always=True)
    def determine_level(cls, v, values):
        """Always derive level from numeric value for consistency."""
        score = values.get('value', 0.0)
        if score >= 0.75:
            return ConfidenceLevel.HIGH
        elif score >= 0.50:
            return ConfidenceLevel.MEDIUM
        elif score >= 0.25:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.UNKNOWN


class Evidence(BaseModel):
    """Citation and source metadata."""
    source: EvidenceSource = Field(..., description="Type of evidence source")
    database: str = Field(..., description="Database name (e.g., PubChem, ChEMBL)")
    identifier: Optional[str] = Field(None, description="Record ID in the database")
    url: Optional[str] = Field(None, description="Direct URL to evidence")
    description: str = Field(..., description="Human-readable description")
    confidence: ConfidenceScore = Field(..., description="Confidence in this evidence")
    retrieved_at: datetime = Field(default_factory=datetime.now, description="Timestamp of retrieval")


class DrugInput(BaseModel):
    """User input schema for drug."""
    name: str = Field(..., description="Drug name (e.g., 'Metformin')")
    pubchem_cid: Optional[int] = Field(None, description="PubChem Compound ID")
    chembl_id: Optional[str] = Field(None, description="ChEMBL ID")
    drugbank_id: Optional[str] = Field(None, description="DrugBank ID")
    smiles: Optional[str] = Field(None, description="SMILES notation")


class DiseaseInput(BaseModel):
    """User input schema for disease."""
    name: str = Field(..., description="Disease name (e.g., 'Alzheimer's disease')")
    mesh_id: Optional[str] = Field(None, description="MeSH ID")
    mondo_id: Optional[str] = Field(None, description="Mondo Disease Ontology ID")
    omim_id: Optional[str] = Field(None, description="OMIM ID")


class Target(BaseModel):
    """Drug target representation."""
    name: str = Field(..., description="Target name (gene/protein)")
    uniprot_id: Optional[str] = Field(None, description="UniProt ID")
    gene_symbol: Optional[str] = Field(None, description="Gene symbol")
    target_type: str = Field(..., description="Type (e.g., 'protein', 'enzyme', 'receptor')")
    activity: Optional[str] = Field(None, description="Activity type (e.g., 'inhibitor', 'agonist')")
    evidence: List[Evidence] = Field(default_factory=list, description="Supporting evidence")


class Pathway(BaseModel):
    """Biological pathway representation."""
    name: str = Field(..., description="Pathway name")
    pathway_id: str = Field(..., description="Pathway ID (e.g., Reactome ID)")
    database: str = Field(..., description="Source database (Reactome, WikiPathways, KEGG)")
    description: Optional[str] = Field(None, description="Pathway description")
    genes: List[str] = Field(default_factory=list, description="Genes involved in pathway")
    relevance_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Relevance to disease")


class MOAChain(BaseModel):
    """Mechanism-of-action chain representation."""
    drug: str = Field(..., description="Drug name")
    targets: List[Target] = Field(..., description="Drug targets")
    pathways: List[Pathway] = Field(default_factory=list, description="Affected pathways")
    mechanism_description: str = Field(..., description="Human-readable mechanism description")
    confidence: ConfidenceScore = Field(..., description="Overall confidence in this MoA")
    evidence: List[Evidence] = Field(default_factory=list, description="Supporting evidence")


class Conflict(BaseModel):
    """Conflicting claim structure."""
    claim_a: str = Field(..., description="First conflicting claim")
    claim_b: str = Field(..., description="Second conflicting claim")
    evidence_a: List[Evidence] = Field(..., description="Evidence for claim A")
    evidence_b: List[Evidence] = Field(..., description="Evidence for claim B")
    resolution: Optional[str] = Field(None, description="How the conflict was resolved")
    confidence_impact: str = Field(..., description="How this affects overall confidence")


class DiseaseRelevance(BaseModel):
    """Disease-mechanism relevance assessment."""
    disease: str = Field(..., description="Disease name")
    mechanism: str = Field(..., description="Mechanism being evaluated")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Relevance score")
    directionality: Literal["beneficial", "harmful", "unclear"] = Field(
        ..., description="Expected effect direction"
    )
    rationale: str = Field(..., description="Biological rationale for relevance")
    disease_genes: List[str] = Field(default_factory=list, description="Disease-associated genes")
    pathway_overlap: List[str] = Field(default_factory=list, description="Overlapping pathways")
    evidence: List[Evidence] = Field(default_factory=list, description="Supporting evidence")


class HypothesisState(BaseModel):
    """Central state object for hypothesis generation."""
    drug_input: DrugInput = Field(..., description="Input drug information")
    disease_input: DiseaseInput = Field(..., description="Input disease information")
    moa_chains: List[MOAChain] = Field(default_factory=list, description="Identified MoA chains")
    disease_relevance: Optional[DiseaseRelevance] = Field(None, description="Disease relevance assessment")
    conflicts: List[Conflict] = Field(default_factory=list, description="Identified conflicts")
    overall_confidence: Optional[ConfidenceScore] = Field(None, description="Overall hypothesis confidence")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")


class NextStep(BaseModel):
    """Suggested next experimental step."""
    step_type: Literal["experimental", "clinical", "literature", "computational"] = Field(
        ..., description="Type of next step"
    )
    description: str = Field(..., description="Detailed description of the step")
    priority: Literal["high", "medium", "low"] = Field(..., description="Priority level")
    rationale: str = Field(..., description="Why this step is recommended")


class HypothesisReport(BaseModel):
    """Final output schema for hypothesis report."""
    drug: str = Field(..., description="Drug name")
    disease: str = Field(..., description="Disease name")
    
    # Executive Summary
    summary: str = Field(..., description="Executive summary of findings")
    recommendation: Literal["promising", "uncertain", "not_recommended"] = Field(
        ..., description="Overall recommendation"
    )
    
    # Mechanistic Rationale
    moa_chains: List[MOAChain] = Field(..., description="Identified mechanisms of action")
    disease_relevance: Optional[DiseaseRelevance] = Field(None, description="Disease relevance assessment")
    
    # Uncertainty & Conflicts
    overall_confidence: ConfidenceScore = Field(..., description="Overall confidence score")
    conflicts: List[Conflict] = Field(default_factory=list, description="Conflicting evidence")
    uncertainties: List[str] = Field(default_factory=list, description="Key uncertainties")
    
    # Evidence
    all_evidence: List[Evidence] = Field(default_factory=list, description="All supporting evidence")
    
    # Next Steps
    suggested_next_steps: List[NextStep] = Field(default_factory=list, description="Recommended next steps")
    
    # Metadata
    generated_at: datetime = Field(default_factory=datetime.now, description="Report generation timestamp")
    processing_time_seconds: Optional[float] = Field(None, description="Total processing time")
    
    class Config:
        json_schema_extra = {
            "example": {
                "drug": "Metformin",
                "disease": "Alzheimer's disease",
                "summary": "Metformin shows potential for Alzheimer's disease through AMPK activation...",
                "recommendation": "uncertain",
                "overall_confidence": {
                    "value": 0.45,
                    "level": "medium",
                    "rationale": "Mixed evidence from preclinical and clinical studies"
                }
            }
        }
