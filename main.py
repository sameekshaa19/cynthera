"""
Main entry point for the Cynthera drug repurposing system.
Can be used for CLI or programmatic access.
"""
import argparse
import asyncio
import os
import sys

from backend.engineering.orchestrator.master_orchestrator import MasterOrchestrator
from backend.core.enums.retrieval_policy import RetrievalPolicy
from utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Cynthera - Agentic AI for Mechanism-Grounded Drug Repurposing"
    )
    
    parser.add_argument(
        "--drug",
        type=str,
        required=True,
        help="Drug name (e.g., 'Sildenafil')"
    )
    
    parser.add_argument(
        "--disease",
        type=str,
        required=True,
        help="Disease name (e.g., 'Pulmonary Arterial Hypertension')"
    )
    
    parser.add_argument(
        "--policy",
        type=str,
        default="STANDARD",
        choices=["STANDARD", "FAST", "COMPREHENSIVE"],
        help="Retrieval policy (default: STANDARD)"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path for JSON report (optional)"
    )
    
    args = parser.parse_args()
    
    # Process
    logger.info(f"Processing: {args.drug} -> {args.disease} (policy: {args.policy})")
    
    orchestrator = MasterOrchestrator(
        llm_api_key=os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    )
    
    policy_map = {
        "STANDARD": RetrievalPolicy.STANDARD,
        "FAST": RetrievalPolicy.FAST,
        "COMPREHENSIVE": RetrievalPolicy.COMPREHENSIVE,
    }
    policy = policy_map.get(args.policy, RetrievalPolicy.STANDARD)
    
    try:
        hypothesis, package, result = asyncio.run(
            orchestrator.evaluate(args.drug, args.disease, policy=policy)
        )
    except Exception as exc:
        logger.critical(f"Pipeline execution failed: {exc}", exc_info=True)
        sys.exit(1)
        
    # Display summary
    print("\n" + "="*60)
    print("CYNTHERA HYPOTHESIS REPORT")
    print("="*60)
    print(f"Drug: {hypothesis.drug_name} (ChEMBL ID: {hypothesis.drug_chembl_id})")
    print(f"Disease: {hypothesis.disease_name} (MeSH ID: {hypothesis.disease_mesh_id})")
    print(f"Recommendation: {result.recommendation_status.value}")
    print(f"Support Score (SS): {result.support_assessment.score:.3f} ({result.support_assessment.level})")
    print(f"Mechanistic Score (MS): {result.mechanistic_assessment.score:.3f} ({result.mechanistic_assessment.level})")
    print(f"Risk Score (RS): {result.risk_assessment.score:.3f} ({result.risk_assessment.level})")
    print(f"\nSummary:\n{result.audit_report.summary}")
    print("="*60)
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            f.write(result.model_dump_json(indent=2))
        print(f"\nFull report saved to: {args.output}")
    
    return result


if __name__ == "__main__":
    main()
