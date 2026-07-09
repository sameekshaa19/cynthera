"""
Main entry point for the Cynthera drug repurposing system.
Can be used for CLI or programmatic access.
"""
import argparse
from models.data_models import DrugInput, DiseaseInput
from orchestrator.orchestrator import MasterOrchestrator
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
        help="Drug name (e.g., 'Metformin')"
    )
    
    parser.add_argument(
        "--disease",
        type=str,
        required=True,
        help="Disease name (e.g., 'Alzheimer's disease')"
    )
    
    parser.add_argument(
        "--pubchem-cid",
        type=int,
        help="PubChem Compound ID (optional)"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path for JSON report (optional)"
    )
    
    args = parser.parse_args()
    
    # Create input objects
    drug_input = DrugInput(
        name=args.drug,
        pubchem_cid=args.pubchem_cid
    )
    
    disease_input = DiseaseInput(
        name=args.disease
    )
    
    # Process
    logger.info(f"Processing: {args.drug} -> {args.disease}")
    orchestrator = MasterOrchestrator()
    report = orchestrator.process(drug_input, disease_input)
    
    # Display summary
    print("\n" + "="*60)
    print("CYNTHERA HYPOTHESIS REPORT")
    print("="*60)
    print(f"Drug: {report.drug}")
    print(f"Disease: {report.disease}")
    print(f"Recommendation: {report.recommendation}")
    print(f"Confidence: {report.overall_confidence.value:.2f} ({report.overall_confidence.level.value})")
    print(f"\nSummary:\n{report.summary}")
    print("="*60)
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report.model_dump_json(indent=2))
        print(f"\nFull report saved to: {args.output}")
    
    return report


if __name__ == "__main__":
    main()
