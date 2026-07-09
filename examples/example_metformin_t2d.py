"""
Example: Metformin for Type 2 Diabetes (Control Case)
This is a known, established use case to validate the system works correctly.
"""
from models.data_models import DrugInput, DiseaseInput
from orchestrator.orchestrator import MasterOrchestrator


def main():
    """Run example for Metformin -> Type 2 Diabetes."""
    print("\n" + "="*60)
    print("EXAMPLE: Metformin for Type 2 Diabetes (Control)")
    print("="*60 + "\n")
    
    # Create inputs
    drug = DrugInput(
        name="Metformin",
        pubchem_cid=4091  # Optional but helps accuracy
    )
    
    disease = DiseaseInput(
        name="Type 2 Diabetes"
    )
    
    # Process
    print("Initializing orchestrator...")
    orchestrator = MasterOrchestrator()
    
    print("Generating hypothesis...\n")
    report = orchestrator.process(drug, disease)
    
    # Display results
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    print(f"\nDrug: {report.drug}")
    print(f"Disease: {report.disease}")
    print(f"\nRecommendation: {report.recommendation.upper()}")
    print(f"Overall Confidence: {report.overall_confidence.value:.2f} ({report.overall_confidence.level.value})")
    
    print(f"\n📝 Summary:")
    print(report.summary)
    
    print(f"\n🔬 Mechanisms Identified: {len(report.moa_chains)}")
    for i, chain in enumerate(report.moa_chains, 1):
        print(f"\n  {i}. {chain.mechanism_description}")
        print(f"     Confidence: {chain.confidence.value:.2f}")
        print(f"     Targets: {len(chain.targets)}")
        print(f"     Pathways: {len(chain.pathways)}")
    
    if report.disease_relevance:
        print(f"\n🎯 Disease Relevance Score: {report.disease_relevance.relevance_score:.2f}")
        print(f"   Directionality: {report.disease_relevance.directionality}")
    
    print(f"\n📚 Evidence Items: {len(report.all_evidence)}")
    
    if report.uncertainties:
        print(f"\n⚠️  Uncertainties ({len(report.uncertainties)}):")
        for unc in report.uncertainties:
            print(f"   - {unc}")
    
    print(f"\n🚀 Suggested Next Steps ({len(report.suggested_next_steps)}):")
    for step in report.suggested_next_steps:
        print(f"   - [{step.priority.upper()}] {step.description}")
    
    print("\n" + "="*60)
    print(f"Processing completed in {report.processing_time_seconds:.2f} seconds")
    print("="*60 + "\n")
    
    # Save report
    output_file = "example_metformin_t2d_report.json"
    with open(output_file, 'w') as f:
        f.write(report.model_dump_json(indent=2))
    print(f"Full report saved to: {output_file}\n")


if __name__ == "__main__":
    main()
