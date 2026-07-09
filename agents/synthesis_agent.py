"""
Hypothesis Synthesis Agent.
Generates final hypothesis report by integrating all agent outputs.
"""
from typing import List
from datetime import datetime

from models.data_models import (
    DrugInput,
    DiseaseInput,
    MOAChain,
    DiseaseRelevance,
    HypothesisReport,
    Evidence,
    Conflict,
    NextStep,
    ConfidenceScore,
    ConfidenceLevel,
)
from utils.logger import get_logger
from utils.confidence_scoring import combine_confidence_scores, penalize_for_conflicts

logger = get_logger(__name__)


class SynthesisAgent:
    """
    Agent responsible for generating final hypothesis reports.
    Integrates outputs from all other agents into a comprehensive report.
    """
    
    def __init__(self):
        """Initialize the synthesis agent."""
        logger.info("Synthesis Agent initialized")
    
    def process(
        self,
        drug_input: DrugInput,
        disease_input: DiseaseInput,
        moa_chains: List[MOAChain],
        disease_relevance: DiseaseRelevance,
        conflicts: List[Conflict] = None,
        processing_time: float = None
    ) -> HypothesisReport:
        """
        Main processing method to generate hypothesis report.
        
        Args:
            drug_input: Drug information
            disease_input: Disease information
            moa_chains: List of MoA chains
            disease_relevance: Disease relevance assessment
            conflicts: List of conflicts (optional)
            processing_time: Total processing time in seconds
        
        Returns:
            Complete HypothesisReport
        """
        logger.info(f"Synthesizing hypothesis for {drug_input.name} -> {disease_input.name}")
        
        conflicts = conflicts or []
        
        # Step 1: Generate executive summary
        summary = self._generate_summary(
            drug_input.name,
            disease_input.name,
            moa_chains,
            disease_relevance
        )
        
        # Step 2: Determine overall recommendation
        recommendation = self._determine_recommendation(disease_relevance, conflicts)
        
        # Step 3: Calculate overall confidence
        overall_confidence = self._calculate_overall_confidence(
            moa_chains,
            disease_relevance,
            conflicts
        )
        
        # Step 4: Identify uncertainties
        uncertainties = self._identify_uncertainties(
            moa_chains,
            disease_relevance,
            conflicts
        )
        
        # Step 5: Aggregate all evidence
        all_evidence = self._aggregate_evidence(moa_chains, disease_relevance)
        
        # Step 6: Suggest next steps
        next_steps = self._suggest_next_steps(
            drug_input.name,
            disease_input.name,
            overall_confidence,
            disease_relevance
        )
        
        # Step 7: Create report
        report = HypothesisReport(
            drug=drug_input.name,
            disease=disease_input.name,
            summary=summary,
            recommendation=recommendation,
            moa_chains=moa_chains,
            disease_relevance=disease_relevance,
            overall_confidence=overall_confidence,
            conflicts=conflicts,
            uncertainties=uncertainties,
            all_evidence=all_evidence,
            suggested_next_steps=next_steps,
            processing_time_seconds=processing_time
        )
        
        logger.info(f"Hypothesis report generated: {recommendation}")
        return report
    
    def _generate_summary(
        self,
        drug_name: str,
        disease_name: str,
        moa_chains: List[MOAChain],
        disease_relevance: DiseaseRelevance
    ) -> str:
        """Generate executive summary."""
        summary_parts = []
        
        # Opening statement
        if disease_relevance and disease_relevance.relevance_score > 0.5:
            summary_parts.append(
                f"{drug_name} shows potential for {disease_name} through mechanism-based reasoning."
            )
        else:
            summary_parts.append(
                f"{drug_name} has limited evidence for {disease_name} based on current analysis."
            )
        
        # Mechanism summary
        if moa_chains:
            num_targets = sum(len(chain.targets) for chain in moa_chains)
            summary_parts.append(
                f"The drug targets {num_targets} protein(s) with identified mechanisms."
            )
        
        # Relevance summary
        if disease_relevance:
            summary_parts.append(
                f"Disease relevance score: {disease_relevance.relevance_score:.2f}. "
                f"{disease_relevance.rationale}"
            )
        
        return " ".join(summary_parts)
    
    def _determine_recommendation(
        self,
        disease_relevance: DiseaseRelevance,
        conflicts: List[Conflict]
    ) -> str:
        """Determine overall recommendation."""
        if not disease_relevance:
            return "not_recommended"
        
        score = disease_relevance.relevance_score
        num_conflicts = len(conflicts)
        
        # Adjust for conflicts
        if num_conflicts > 2:
            return "uncertain"
        
        if score >= 0.6:
            return "promising"
        elif score >= 0.4:
            return "uncertain"
        else:
            return "not_recommended"
    
    def _calculate_overall_confidence(
        self,
        moa_chains: List[MOAChain],
        disease_relevance: DiseaseRelevance,
        conflicts: List[Conflict]
    ) -> ConfidenceScore:
        """Calculate overall confidence score."""
        confidence_scores = []
        
        # MoA confidence
        for chain in moa_chains:
            confidence_scores.append(chain.confidence)
        
        # Disease relevance as confidence
        if disease_relevance:
            relevance_confidence = ConfidenceScore(
                value=disease_relevance.relevance_score,
                level=ConfidenceLevel.MEDIUM,
                rationale="Disease relevance score"
            )
            confidence_scores.append(relevance_confidence)
        
        # Combine scores (conservative approach)
        if confidence_scores:
            combined = combine_confidence_scores(confidence_scores, method="conservative")
        else:
            combined = ConfidenceScore(
                value=0.2,
                level=ConfidenceLevel.LOW,
                rationale="Insufficient data"
            )
        
        # Penalize for conflicts
        final_confidence = penalize_for_conflicts(combined, len(conflicts))
        
        return final_confidence
    
    def _identify_uncertainties(
        self,
        moa_chains: List[MOAChain],
        disease_relevance: DiseaseRelevance,
        conflicts: List[Conflict]
    ) -> List[str]:
        """Identify key uncertainties."""
        uncertainties = []
        
        # Check for low confidence mechanisms
        for chain in moa_chains:
            if chain.confidence.value < 0.5:
                uncertainties.append(
                    f"Low confidence in mechanism: {chain.mechanism_description}"
                )
        
        # Check for unclear directionality
        if disease_relevance and disease_relevance.directionality == "unclear":
            uncertainties.append(
                "Directionality of effect (beneficial vs harmful) is unclear"
            )
        
        # Check for limited pathway overlap
        if disease_relevance and len(disease_relevance.pathway_overlap) == 0:
            uncertainties.append(
                "No clear pathway overlap between drug mechanism and disease biology"
            )
        
        # Add conflicts as uncertainties
        for conflict in conflicts:
            uncertainties.append(
                f"Conflicting evidence: {conflict.claim_a} vs {conflict.claim_b}"
            )
        
        # Check for limited evidence
        if not moa_chains or len(moa_chains[0].evidence) < 3:
            uncertainties.append(
                "Limited evidence available from databases"
            )
        
        return uncertainties
    
    def _aggregate_evidence(
        self,
        moa_chains: List[MOAChain],
        disease_relevance: DiseaseRelevance
    ) -> List[Evidence]:
        """Aggregate all evidence from different sources."""
        all_evidence = []
        
        for chain in moa_chains:
            all_evidence.extend(chain.evidence)
        
        if disease_relevance:
            all_evidence.extend(disease_relevance.evidence)
        
        # Deduplicate by identifier
        unique_evidence = {}
        for ev in all_evidence:
            key = f"{ev.database}:{ev.identifier}"
            if key not in unique_evidence:
                unique_evidence[key] = ev
        
        return list(unique_evidence.values())
    
    def _suggest_next_steps(
        self,
        drug_name: str,
        disease_name: str,
        overall_confidence: ConfidenceScore,
        disease_relevance: DiseaseRelevance
    ) -> List[NextStep]:
        """Suggest next experimental steps."""
        next_steps = []
        
        # Literature review
        next_steps.append(NextStep(
            step_type="literature",
            description=f"Conduct comprehensive literature review for {drug_name} in {disease_name}",
            priority="high",
            rationale="Validate computational predictions with published evidence"
        ))
        
        # Experimental validation
        if overall_confidence.value > 0.5:
            next_steps.append(NextStep(
                step_type="experimental",
                description=f"In vitro assays to validate mechanism in {disease_name} models",
                priority="high",
                rationale="Promising computational evidence warrants experimental validation"
            ))
        else:
            next_steps.append(NextStep(
                step_type="computational",
                description="Expand database search and pathway analysis",
                priority="medium",
                rationale="Gather more evidence before experimental validation"
            ))
        
        # Clinical investigation
        if overall_confidence.value > 0.6:
            next_steps.append(NextStep(
                step_type="clinical",
                description=f"Search for ongoing or completed clinical trials of {drug_name} for {disease_name}",
                priority="medium",
                rationale="High confidence suggests potential clinical relevance"
            ))
        
        return next_steps
