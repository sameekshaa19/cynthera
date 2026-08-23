"""
Master Orchestrator for the Cynthera drug repurposing system.
Coordinates execution of all agents and manages the hypothesis generation workflow.
"""
import time
from typing import Optional

from models.data_models import (
    DrugInput,
    DiseaseInput,
    HypothesisReport,
    HypothesisState,
    Conflict,
)
from agents.moa_enumeration_agent import MoAEnumerationAgent
from agents.moa_cross_verification_agent import MoACrossVerificationAgent
from agents.disease_relevance_agent import DiseaseRelevanceAgent
from agents.synthesis_agent import SynthesisAgent
from utils.logger import get_logger

logger = get_logger(__name__)


class MasterOrchestrator:
    """
    Master orchestrator that coordinates all agents.
    Manages the workflow from drug+disease input to final hypothesis report.
    """
    
    def __init__(self):
        """Initialize the orchestrator with all agents."""
        logger.info("Initializing Master Orchestrator")
        
        self.moa_agent = MoAEnumerationAgent()
        self.cross_verification_agent = MoACrossVerificationAgent()
        self.disease_agent = DiseaseRelevanceAgent()
        self.synthesis_agent = SynthesisAgent()
        
        logger.info("Master Orchestrator initialized successfully")
    
    def process(
        self,
        drug_input: DrugInput,
        disease_input: DiseaseInput
    ) -> HypothesisReport:
        """
        Main processing method to generate hypothesis report.
        
        Workflow:
        1. Initialize hypothesis state
        2. MoA Enumeration: Identify drug targets and mechanisms
        3. Cross-Verification: Validate targets, score strengths, detect conflicts
        4. Disease Relevance: Evaluate mechanism-disease alignment
        5. Synthesis: Generate final hypothesis report
        
        Args:
            drug_input: Drug information
            disease_input: Disease information
        
        Returns:
            Complete HypothesisReport
        """
        start_time = time.time()
        
        logger.info("="*60)
        logger.info(f"Starting hypothesis generation")
        logger.info(f"Drug: {drug_input.name}")
        logger.info(f"Disease: {disease_input.name}")
        logger.info("="*60)
        
        # Step 1: Initialize state
        state = HypothesisState(
            drug_input=drug_input,
            disease_input=disease_input
        )
        logger.info("Hypothesis state initialized")
        
        try:
            # Step 2: MoA Enumeration
            logger.info("\n--- Phase 1: MoA Enumeration ---")
            moa_chains = self.moa_agent.process(drug_input)
            state.moa_chains = moa_chains
            
            if not moa_chains:
                logger.warning("No mechanisms of action identified")
                return self._generate_empty_report(
                    drug_input,
                    disease_input,
                    "No mechanisms of action could be identified for this drug",
                    time.time() - start_time
                )
            
            logger.info(f"Identified {len(moa_chains)} MoA chain(s)")
            
            # Step 3: Cross-Verification (biological quality gate)
            logger.info("\n--- Phase 1.5: MoA Cross-Verification ---")
            verified_chains, conflicts, verification_summary = (
                self.cross_verification_agent.process(moa_chains)
            )
            state.moa_chains = verified_chains
            state.conflicts = conflicts
            
            if not verified_chains:
                logger.warning("No MoA chains survived cross-verification")
                return self._generate_empty_report(
                    drug_input,
                    disease_input,
                    "No verified mechanisms of action after quality filtering",
                    time.time() - start_time
                )
            
            # Step 4: Disease Relevance Assessment
            logger.info("\n--- Phase 2: Disease Relevance Assessment ---")
            disease_relevance = self.disease_agent.process(disease_input, verified_chains)
            state.disease_relevance = disease_relevance
            
            if not disease_relevance:
                logger.warning("Could not assess disease relevance")
                return self._generate_empty_report(
                    drug_input,
                    disease_input,
                    "Could not assess relevance of drug mechanisms to disease",
                    time.time() - start_time
                )
            
            logger.info(f"Disease relevance score: {disease_relevance.relevance_score:.2f}")
            
            # Step 5: Synthesis
            logger.info("\n--- Phase 3: Hypothesis Synthesis ---")
            processing_time = time.time() - start_time
            
            report = self.synthesis_agent.process(
                drug_input=drug_input,
                disease_input=disease_input,
                moa_chains=verified_chains,
                disease_relevance=disease_relevance,
                conflicts=conflicts,
                processing_time=processing_time
            )
            
            logger.info("="*60)
            logger.info(f"Hypothesis generation completed in {processing_time:.2f}s")
            logger.info(f"Recommendation: {report.recommendation}")
            logger.info(f"Overall confidence: {report.overall_confidence.value:.2f} ({report.overall_confidence.level.value})")
            logger.info(f"Verification: {verification_summary}")
            logger.info("="*60)
            
            return report
        
        except Exception as e:
            logger.error(f"Error during hypothesis generation: {e}", exc_info=True)
            return self._generate_error_report(
                drug_input,
                disease_input,
                str(e),
                time.time() - start_time
            )
    
    def _generate_empty_report(
        self,
        drug_input: DrugInput,
        disease_input: DiseaseInput,
        reason: str,
        processing_time: float
    ) -> HypothesisReport:
        """Generate a report when no data is available."""
        from models.data_models import ConfidenceScore, ConfidenceLevel
        
        return HypothesisReport(
            drug=drug_input.name,
            disease=disease_input.name,
            summary=f"Unable to generate hypothesis: {reason}",
            recommendation="not_recommended",
            moa_chains=[],
            overall_confidence=ConfidenceScore(
                value=0.0,
                level=ConfidenceLevel.UNKNOWN,
                rationale=reason
            ),
            uncertainties=[reason],
            processing_time_seconds=processing_time
        )
    
    def _generate_error_report(
        self,
        drug_input: DrugInput,
        disease_input: DiseaseInput,
        error_message: str,
        processing_time: float
    ) -> HypothesisReport:
        """Generate a report when an error occurs."""
        from models.data_models import ConfidenceScore, ConfidenceLevel
        
        return HypothesisReport(
            drug=drug_input.name,
            disease=disease_input.name,
            summary=f"Error during hypothesis generation: {error_message}",
            recommendation="not_recommended",
            moa_chains=[],
            overall_confidence=ConfidenceScore(
                value=0.0,
                level=ConfidenceLevel.UNKNOWN,
                rationale="Processing error"
            ),
            uncertainties=[f"Error: {error_message}"],
            processing_time_seconds=processing_time
        )
