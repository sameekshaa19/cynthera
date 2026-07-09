"""
Disease-Mechanism Relevance Agent.
Evaluates how relevant drug mechanisms are to disease biology.
"""
from typing import List, Optional
from models.data_models import (
    DiseaseInput,
    MOAChain,
    DiseaseRelevance,
    Evidence,
    EvidenceSource,
    ConfidenceScore,
    ConfidenceLevel,
)
from data.database_connectors import DisGeNETConnector, PubMedConnector
from utils.logger import get_logger
from utils.confidence_scoring import calculate_pathway_relevance_score, aggregate_evidence_confidence

logger = get_logger(__name__)


class DiseaseRelevanceAgent:
    """
    Agent responsible for evaluating disease-mechanism alignment.
    Assesses pathway relevance to disease biology and determines directionality.
    """
    
    def __init__(self):
        """Initialize the agent with database connectors."""
        self.disgenet = DisGeNETConnector()
        self.pubmed = PubMedConnector()
        logger.info("Disease Relevance Agent initialized")
    
    def process(
        self,
        disease_input: DiseaseInput,
        moa_chains: List[MOAChain]
    ) -> Optional[DiseaseRelevance]:
        """
        Main processing method to evaluate disease-mechanism relevance.
        
        Args:
            disease_input: Disease information
            moa_chains: List of MoA chains from MoA Enumeration Agent
        
        Returns:
            DiseaseRelevance object or None if no relevance found
        """
        logger.info(f"Evaluating relevance for disease: {disease_input.name}")
        
        if not moa_chains:
            logger.warning("No MoA chains provided")
            return None
        
        # Step 1: Get disease-associated genes
        disease_genes = self._get_disease_genes(disease_input)
        
        # Step 2: Extract drug targets and pathways from MoA chains
        drug_targets = []
        pathways = []
        for chain in moa_chains:
            drug_targets.extend([t.gene_symbol or t.name for t in chain.targets])
            pathways.extend(chain.pathways)
        
        # Step 3: Calculate pathway relevance
        pathway_overlaps = []
        for pathway in pathways:
            relevance = calculate_pathway_relevance_score(
                pathway_genes=pathway.genes,
                disease_genes=disease_genes,
                drug_targets=drug_targets
            )
            pathway.relevance_score = relevance
            if relevance > 0:
                pathway_overlaps.append(pathway.name)
        
        # Step 4: Search literature for disease-drug associations
        literature_evidence = self._search_literature(
            disease_input.name,
            moa_chains[0].drug
        )
        
        # Step 5: Determine directionality
        directionality = self._determine_directionality(
            moa_chains,
            disease_genes,
            disease_input.name
        )
        
        # Step 6: Calculate overall relevance score
        relevance_score = self._calculate_relevance_score(
            pathways,
            disease_genes,
            drug_targets
        )
        
        # Step 7: Generate rationale
        rationale = self._generate_rationale(
            disease_input.name,
            moa_chains[0].drug,
            disease_genes,
            drug_targets,
            pathway_overlaps
        )
        
        # Step 8: Aggregate evidence
        all_evidence = literature_evidence
        for chain in moa_chains:
            all_evidence.extend(chain.evidence)
        
        disease_relevance = DiseaseRelevance(
            disease=disease_input.name,
            mechanism=moa_chains[0].mechanism_description,
            relevance_score=relevance_score,
            directionality=directionality,
            rationale=rationale,
            disease_genes=disease_genes,
            pathway_overlap=pathway_overlaps,
            evidence=all_evidence
        )
        
        logger.info(f"Relevance score: {relevance_score:.2f}, Directionality: {directionality}")
        return disease_relevance
    
    def _get_disease_genes(self, disease_input: DiseaseInput) -> List[str]:
        """Get genes associated with the disease.
        
        Strategy:
        1. Try DisGeNET (if API key available)
        2. Fallback to OpenTargets Platform (free, no key needed)
        """
        disease_genes = []
        
        # Source 1: DisGeNET
        try:
            gene_data = self.disgenet.get_disease_genes(disease_input.name)
            for item in gene_data:
                if 'gene_symbol' in item:
                    disease_genes.append(item['gene_symbol'])
        except Exception as e:
            logger.error(f"Error fetching DisGeNET disease genes: {e}")
        
        # Source 2: OpenTargets Platform (free GraphQL API, no key needed)
        if not disease_genes:
            disease_genes = self._get_opentargets_disease_genes(disease_input.name)
        
        if disease_genes:
            logger.info(
                f"Found {len(disease_genes)} disease genes for {disease_input.name}: "
                f"{', '.join(disease_genes[:10])}"
            )
        else:
            logger.warning(f"No disease genes found for {disease_input.name}")
        
        return disease_genes
    
    def _get_opentargets_disease_genes(self, disease_name: str) -> List[str]:
        """
        Get disease-associated genes from OpenTargets Platform.
        
        OpenTargets provides a free GraphQL API with no authentication required.
        It aggregates gene-disease associations from multiple sources including
        GWAS, rare disease databases, literature mining, etc.
        """
        import requests
        
        url = "https://api.platform.opentargets.org/api/v4/graphql"
        
        # Step 1: Search for the disease to get its EFO ID
        search_query = """
        query SearchDisease($queryString: String!) {
            search(queryString: $queryString, entityNames: ["disease"], page: {size: 1, index: 0}) {
                hits {
                    id
                    name
                    entity
                }
            }
        }
        """
        
        try:
            response = requests.post(
                url,
                json={"query": search_query, "variables": {"queryString": disease_name}},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            response.raise_for_status()
            search_data = response.json()
            
            hits = search_data.get("data", {}).get("search", {}).get("hits", [])
            if not hits:
                logger.warning(f"No OpenTargets disease match for: {disease_name}")
                return []
            
            disease_id = hits[0]["id"]
            disease_matched = hits[0].get("name", disease_name)
            logger.info(f"OpenTargets matched '{disease_name}' -> '{disease_matched}' ({disease_id})")
            
            # Step 2: Get associated targets (genes) for this disease
            targets_query = """
            query DiseaseTargets($efoId: String!) {
                disease(efoId: $efoId) {
                    associatedTargets(page: {size: 25, index: 0}) {
                        rows {
                            target {
                                approvedSymbol
                                approvedName
                            }
                            score
                        }
                    }
                }
            }
            """
            
            response = requests.post(
                url,
                json={"query": targets_query, "variables": {"efoId": disease_id}},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            response.raise_for_status()
            targets_data = response.json()
            
            rows = (
                targets_data.get("data", {})
                .get("disease", {})
                .get("associatedTargets", {})
                .get("rows", [])
            )
            
            genes = []
            for row in rows:
                symbol = row.get("target", {}).get("approvedSymbol")
                score = row.get("score", 0)
                if symbol and score > 0.1:  # Filter low-confidence associations
                    genes.append(symbol)
            
            logger.info(
                f"OpenTargets returned {len(genes)} genes for "
                f"{disease_matched} (from {len(rows)} total associations)"
            )
            return genes
            
        except Exception as e:
            logger.error(f"Error fetching OpenTargets disease genes: {e}")
            return []
    
    def _search_literature(self, disease_name: str, drug_name: str) -> List[Evidence]:
        """Search PubMed for disease-drug associations."""
        evidence_list = []
        
        try:
            query = f"{drug_name} AND {disease_name}"
            pmids = self.pubmed.search(query, max_results=5)
            
            if pmids:
                for pmid in pmids:
                    evidence = Evidence(
                        source=EvidenceSource.LITERATURE,
                        database="PubMed",
                        identifier=pmid,
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        description=f"Literature evidence for {drug_name} in {disease_name}",
                        confidence=ConfidenceScore(
                            value=0.6,
                            level=ConfidenceLevel.MEDIUM,
                            rationale="Published literature"
                        )
                    )
                    evidence_list.append(evidence)
                
                logger.info(f"Found {len(pmids)} PubMed articles")
        
        except Exception as e:
            logger.error(f"Error searching PubMed: {e}")
        
        return evidence_list
    
    def _determine_directionality(
        self,
        moa_chains: List[MOAChain],
        disease_genes: List[str],
        disease_name: str
    ) -> str:
        """
        Determine if the mechanism is beneficial, harmful, or unclear.
        
        This is a simplified heuristic for MVP.
        In production, would use more sophisticated reasoning.
        """
        # Check target activities
        activities = []
        for chain in moa_chains:
            for target in chain.targets:
                if target.activity:
                    activities.append(target.activity.lower())
        
        # Simple heuristic based on common patterns
        # This would be much more sophisticated in production
        if any(act in ['inhibitor', 'antagonist', 'blocker'] for act in activities):
            # Inhibition - depends on whether target is overactive in disease
            return "unclear"  # Would need disease-specific knowledge
        elif any(act in ['agonist', 'activator'] for act in activities):
            return "unclear"
        else:
            return "unclear"
        
        # For MVP, default to unclear unless we have strong evidence
        # In production, would integrate disease pathway knowledge
    
    def _calculate_relevance_score(
        self,
        pathways: List,
        disease_genes: List[str],
        drug_targets: List[str]
    ) -> float:
        """Calculate overall relevance score."""
        if not pathways:
            return 0.3  # Low baseline if no pathways
        
        # Average pathway relevance scores
        pathway_scores = [p.relevance_score for p in pathways if p.relevance_score is not None]
        
        if pathway_scores:
            avg_score = sum(pathway_scores) / len(pathway_scores)
        else:
            avg_score = 0.3
        
        # Boost if we have disease genes
        if disease_genes:
            avg_score = min(avg_score * 1.2, 1.0)
        
        return round(avg_score, 2)
    
    def _generate_rationale(
        self,
        disease_name: str,
        drug_name: str,
        disease_genes: List[str],
        drug_targets: List[str],
        pathway_overlaps: List[str]
    ) -> str:
        """Generate human-readable rationale."""
        rationale_parts = []
        
        if drug_targets:
            rationale_parts.append(
                f"{drug_name} targets {len(drug_targets)} protein(s)"
            )
        
        if disease_genes:
            rationale_parts.append(
                f"{disease_name} is associated with {len(disease_genes)} gene(s)"
            )
        
        if pathway_overlaps:
            rationale_parts.append(
                f"Overlapping pathways: {', '.join(pathway_overlaps[:3])}"
            )
        else:
            rationale_parts.append(
                "Limited pathway overlap identified"
            )
        
        return ". ".join(rationale_parts) + "."
