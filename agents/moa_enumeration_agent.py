"""
MoA (Mechanism of Action) & Target Enumeration Agent.
Identifies drug targets and mechanisms from multiple databases.
"""
from typing import List, Optional, Dict
from datetime import datetime

from models.data_models import (
    DrugInput,
    Target,
    Pathway,
    MOAChain,
    Evidence,
    EvidenceSource,
    ConfidenceScore,
    ConfidenceLevel,
)
from data.database_connectors import PubChemConnector, ChEMBLConnector, ReactomeConnector
from utils.logger import get_logger
from utils.confidence_scoring import aggregate_evidence_confidence

logger = get_logger(__name__)


class MoAEnumerationAgent:
    """
    Agent responsible for identifying drug targets and mechanisms of action.
    Queries multiple databases and generates candidate MoA chains.
    """
    
    def __init__(self):
        """Initialize the agent with database connectors."""
        self.pubchem = PubChemConnector()
        self.chembl = ChEMBLConnector()
        self.reactome = ReactomeConnector()
        logger.info("MoA Enumeration Agent initialized")
    
    def process(self, drug_input: DrugInput) -> List[MOAChain]:
        """
        Main processing method to enumerate mechanisms of action.
        
        Args:
            drug_input: Drug information
        
        Returns:
            List of MOAChain objects with identified mechanisms
        """
        logger.info(f"Processing drug: {drug_input.name}")
        
        # Step 1: Get compound ID if not provided
        pubchem_cid = drug_input.pubchem_cid
        if not pubchem_cid:
            pubchem_cid = self._get_pubchem_id(drug_input.name)
        
        # Step 2: Identify targets from multiple sources
        targets = self._identify_targets(drug_input, pubchem_cid)
        
        if not targets:
            logger.warning(f"No targets found for {drug_input.name}")
            return []
        
        # Step 3: Map targets to pathways
        pathways = self._map_targets_to_pathways(targets)
        
        # Step 4: Generate MoA chains
        moa_chains = self._generate_moa_chains(drug_input.name, targets, pathways)
        
        logger.info(f"Generated {len(moa_chains)} MoA chains for {drug_input.name}")
        return moa_chains
    
    def _get_pubchem_id(self, drug_name: str) -> Optional[int]:
        """Get PubChem CID from drug name."""
        try:
            data = self.pubchem.get_compound_by_name(drug_name)
            if data and 'PC_Compounds' in data:
                cid = data['PC_Compounds'][0]['id']['id']['cid']
                logger.info(f"Found PubChem CID {cid} for {drug_name}")
                return cid
        except Exception as e:
            logger.error(f"Error fetching PubChem ID for {drug_name}: {e}")
        return None
    
    # Blacklist of non-protein target names from bioactivity data
    # These are cell lines, assay artifacts, or generic labels
    GARBAGE_TARGET_NAMES = {
        'unchecked', 'unknown', 'unknown target', 'k562', 'hela',
        'hek293', 'cho', 'jurkat', 'mcf-7', 'mcf7', 'a549',
        'not determined', 'not assigned', 'unspecified',
    }
    
    def _identify_targets(self, drug_input: DrugInput, pubchem_cid: Optional[int]) -> List[Target]:
        """Identify drug targets from multiple databases."""
        targets = []
        
        # From PubChem
        if pubchem_cid:
            pubchem_targets = self._get_pubchem_targets(pubchem_cid, drug_input.name)
            targets.extend(pubchem_targets)
        
        # From ChEMBL
        if drug_input.chembl_id:
            chembl_targets = self._get_chembl_targets(drug_input.chembl_id, drug_input.name)
            targets.extend(chembl_targets)
        else:
            # Try to find ChEMBL ID
            chembl_targets = self._search_chembl_targets(drug_input.name)
            targets.extend(chembl_targets)
        
        # Filter out garbage/non-protein targets
        targets = [
            t for t in targets
            if t.name.lower().strip() not in self.GARBAGE_TARGET_NAMES
        ]
        
        # Deduplicate targets by chembl_id or gene_symbol (not description text)
        unique_targets: Dict[str, Target] = {}
        for target in targets:
            # Use gene_symbol as primary dedup key, fall back to name
            dedup_key = target.gene_symbol or target.uniprot_id or target.name
            dedup_key = dedup_key.lower().strip()
            
            if dedup_key not in unique_targets:
                unique_targets[dedup_key] = target
            else:
                # Merge evidence from duplicate targets
                unique_targets[dedup_key].evidence.extend(target.evidence)
        
        result = list(unique_targets.values())
        logger.info(f"Total unique targets found: {len(result)}")
        return result
    
    def _get_pubchem_targets(self, cid: int, drug_name: str) -> List[Target]:
        """Get targets from PubChem's protein target endpoint."""
        targets = []
        try:
            target_data = self.pubchem.get_compound_targets(cid)
            
            for item in target_data:
                protein_name = item.get('ProteinName', '')
                gene_id = item.get('GeneID')
                gene_symbol = item.get('GeneSymbol', '')
                
                if not protein_name:
                    continue
                
                evidence = Evidence(
                    source=EvidenceSource.EXPERIMENTAL,
                    database="PubChem",
                    identifier=str(cid),
                    url=f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                    description=f"PubChem protein target: {protein_name}",
                    confidence=ConfidenceScore(
                        value=0.6,
                        level=ConfidenceLevel.MEDIUM,
                        rationale="Protein target from PubChem bioassay data"
                    )
                )
                
                target = Target(
                    name=protein_name,
                    gene_symbol=gene_symbol if gene_symbol else None,
                    target_type="protein",
                    evidence=[evidence]
                )
                targets.append(target)
            
            if targets:
                logger.info(f"Found {len(targets)} targets from PubChem for CID {cid}")
            else:
                logger.info(f"No protein targets in PubChem for CID {cid}")
                
        except Exception as e:
            logger.error(f"Error fetching PubChem targets for CID {cid}: {e}")
        
        return targets
    
    def _get_chembl_targets(self, chembl_id: str, drug_name: str) -> List[Target]:
        """Get targets from ChEMBL mechanism data with proper field extraction."""
        targets = []
        try:
            mechanisms = self.chembl.get_mechanism(chembl_id)
            
            for mech in mechanisms:
                logger.debug(f"ChEMBL mechanism record: {mech}")
                
                target_chembl_id = mech.get('target_chembl_id')
                if not target_chembl_id:
                    continue
                
                # FIX #1: Use target_pref_name (actual protein), NOT mechanism_of_action (text description)
                target_name = mech.get('target_pref_name') or mech.get('mechanism_of_action', 'Unknown target')
                mechanism_text = mech.get('mechanism_of_action', '')
                activity = mech.get('action_type', 'Unknown')
                
                # Try to resolve gene_symbol from the ChEMBL target endpoint
                gene_symbol = None
                uniprot_id = None
                gene_symbol, uniprot_id = self._resolve_target_gene(target_chembl_id)
                
                evidence = Evidence(
                    source=EvidenceSource.CURATED,
                    database="ChEMBL",
                    identifier=chembl_id,
                    url=f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/",
                    description=f"Mechanism: {mechanism_text}" if mechanism_text else f"Target: {target_name}",
                    confidence=ConfidenceScore(
                        value=0.8,
                        level=ConfidenceLevel.HIGH,
                        rationale="Curated mechanism from ChEMBL"
                    )
                )
                
                target = Target(
                    name=target_name,
                    gene_symbol=gene_symbol,
                    uniprot_id=uniprot_id,
                    target_type="protein",
                    activity=activity,
                    evidence=[evidence]
                )
                targets.append(target)
                logger.info(
                    f"ChEMBL target: {target_name} | gene_symbol={gene_symbol} | "
                    f"activity={activity} | mechanism={mechanism_text}"
                )
        
        except Exception as e:
            logger.error(f"Error fetching ChEMBL targets: {e}")
        
        return targets
    
    def _resolve_target_gene(self, target_chembl_id: str) -> tuple:
        """
        Resolve a target_chembl_id to its gene symbol and UniProt ID
        using the ChEMBL target detail endpoint.
        
        Returns:
            (gene_symbol, uniprot_id) tuple, either can be None
        """
        gene_symbol = None
        uniprot_id = None
        
        try:
            target_data = self.chembl.get_target_details(target_chembl_id)
            if not target_data:
                return gene_symbol, uniprot_id
            
            # ChEMBL target response has 'target_components' with accession and gene info
            components = target_data.get('target_components', [])
            if components:
                component = components[0]  # Take the first component
                accession = component.get('accession')
                if accession:
                    uniprot_id = accession
                
                # target_component_synonyms contains gene symbols
                synonyms = component.get('target_component_synonyms', [])
                for syn in synonyms:
                    if syn.get('syn_type') == 'GENE_SYMBOL':
                        gene_symbol = syn.get('component_synonym')
                        break
                
                # Fallback: if no GENE_SYMBOL synonym, try component description
                if not gene_symbol:
                    for syn in synonyms:
                        if syn.get('syn_type') in ('UNIPROT', 'EC_NUMBER'):
                            continue
                        candidate = syn.get('component_synonym', '')
                        # Gene symbols are typically short uppercase strings
                        if candidate and len(candidate) <= 15 and candidate == candidate.upper():
                            gene_symbol = candidate
                            break
            
            logger.debug(
                f"Resolved {target_chembl_id} -> gene={gene_symbol}, uniprot={uniprot_id}"
            )
        except Exception as e:
            logger.error(f"Error resolving target {target_chembl_id}: {e}")
        
        return gene_symbol, uniprot_id
    
    def _search_chembl_targets(self, drug_name: str) -> List[Target]:
        """Search ChEMBL for drug and get targets."""
        targets = []
        try:
            search_results = self.chembl.search_molecule(drug_name)
            
            if search_results and 'molecules' in search_results:
                molecules = search_results['molecules']
                if molecules:
                    chembl_id = molecules[0].get('molecule_chembl_id')
                    if chembl_id:
                        logger.info(f"Found ChEMBL ID: {chembl_id} for {drug_name}")
                        
                        # Try mechanism data first (best quality)
                        targets = self._get_chembl_targets(chembl_id, drug_name)
                        
                        # Fallback: If no mechanisms, use bioactivity data
                        if not targets:
                            logger.info(f"No mechanisms found, trying bioactivity data for {chembl_id}")
                            targets = self._get_chembl_bioactivity_targets(chembl_id, drug_name)
        
        except Exception as e:
            logger.error(f"Error searching ChEMBL: {e}")
        
        return targets
    
    def _get_chembl_bioactivity_targets(self, chembl_id: str, drug_name: str) -> List[Target]:
        """Get targets from ChEMBL bioactivity data (fallback when mechanisms unavailable)."""
        targets = []
        try:
            activities = self.chembl.get_bioactivity(chembl_id)
            
            # Group by target and keep only high-confidence activities
            target_dict: Dict[str, Dict] = {}
            for activity in activities:
                target_chembl_id = activity.get('target_chembl_id')
                target_name = activity.get('target_pref_name', 'Unknown target')
                activity_type = activity.get('standard_type')
                activity_value = activity.get('standard_value')
                
                # Only include if we have target info
                if target_chembl_id and target_name != 'Unknown target':
                    if target_name not in target_dict:
                        target_dict[target_name] = {
                            'chembl_id': target_chembl_id,
                            'activities': []
                        }
                    target_dict[target_name]['activities'].append({
                        'type': activity_type,
                        'value': activity_value
                    })
            
            # Create Target objects for unique targets
            for target_name, target_info in list(target_dict.items())[:10]:  # Limit to top 10
                # Resolve gene symbol from ChEMBL target details
                gene_symbol, uniprot_id = self._resolve_target_gene(target_info['chembl_id'])
                
                # FILTER: Only accept targets with molecular identity
                # This removes ORGANISM, CELL-LINE, ADMET entries
                if not gene_symbol and not uniprot_id:
                    logger.debug(
                        f"Skipping bioactivity target '{target_name}': "
                        f"no gene_symbol or uniprot_id"
                    )
                    continue
                
                evidence = Evidence(
                    source=EvidenceSource.EXPERIMENTAL,
                    database="ChEMBL",
                    identifier=chembl_id,
                    url=f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/",
                    description=f"Bioactivity data for {drug_name} against {target_name}",
                    confidence=ConfidenceScore(
                        value=0.6,
                        level=ConfidenceLevel.MEDIUM,
                        rationale="Experimental bioactivity data from ChEMBL"
                    )
                )
                
                target = Target(
                    name=target_name,
                    gene_symbol=gene_symbol,
                    uniprot_id=uniprot_id,
                    target_type="protein",
                    evidence=[evidence]
                )
                targets.append(target)
            
            logger.info(f"Found {len(targets)} targets from bioactivity data")
        
        except Exception as e:
            logger.error(f"Error fetching ChEMBL bioactivity: {e}")
        
        return targets
    
    def _map_targets_to_pathways(self, targets: List[Target]) -> List[Pathway]:
        """Map drug targets to biological pathways.
        
        Strategy:
        1. If target has UniProt accession -> use get_pathways_by_uniprot (most reliable)
        2. Else if target has gene_symbol -> use get_pathways_by_gene (search fallback)
        3. Else skip
        """
        pathways = []
        
        for target in targets:
            gene_symbol = target.gene_symbol or target.name
            uniprot_id = target.uniprot_id
            
            try:
                pathway_data = []
                
                # Primary: UniProt accession (Reactome entity endpoint)
                if uniprot_id:
                    logger.info(
                        f"Looking up Reactome pathways via UniProt: {uniprot_id} "
                        f"(target: {target.name}, gene: {gene_symbol})"
                    )
                    pathway_data = self.reactome.get_pathways_by_uniprot(uniprot_id)
                
                # Fallback: gene symbol search
                if not pathway_data and target.gene_symbol:
                    logger.info(
                        f"UniProt lookup empty, falling back to gene search: {target.gene_symbol}"
                    )
                    pathway_data = self.reactome.get_pathways_by_gene(target.gene_symbol)
                
                if not pathway_data:
                    logger.warning(
                        f"No Reactome pathways found for target '{target.name}' "
                        f"(uniprot={uniprot_id}, gene={target.gene_symbol})"
                    )
                    continue
                
                for pw_item in pathway_data:
                    pathway = Pathway(
                        name=pw_item.get('displayName', 'Unknown pathway'),
                        pathway_id=pw_item.get('stId', ''),
                        database="Reactome",
                        description=(
                            pw_item.get('summation', [{}])[0].get('text', '')
                            if pw_item.get('summation') else ''
                        ),
                        genes=[target.gene_symbol or target.name]
                    )
                    pathways.append(pathway)
                
                logger.info(
                    f"Found {len(pathway_data)} pathways for {target.name} "
                    f"(gene={target.gene_symbol}, uniprot={uniprot_id})"
                )
            
            except Exception as e:
                logger.error(
                    f"Error mapping target {target.name} "
                    f"(gene={target.gene_symbol}, uniprot={uniprot_id}) to pathways: {e}"
                )
        
        # Deduplicate pathways by pathway_id
        unique_pathways: Dict[str, Pathway] = {}
        for pw in pathways:
            key = pw.pathway_id or pw.name
            if key not in unique_pathways:
                unique_pathways[key] = pw
            else:
                # Merge gene lists
                existing_genes = set(unique_pathways[key].genes)
                existing_genes.update(pw.genes)
                unique_pathways[key].genes = list(existing_genes)
        
        result = list(unique_pathways.values())
        logger.info(f"Total unique pathways mapped: {len(result)}")
        return result
    
    def _generate_moa_chains(
        self,
        drug_name: str,
        targets: List[Target],
        pathways: List[Pathway]
    ) -> List[MOAChain]:
        """Generate MoA chains from targets and pathways."""
        moa_chains = []
        
        # Collect all evidence
        all_evidence = []
        for target in targets:
            all_evidence.extend(target.evidence)
        
        # Calculate overall confidence
        if all_evidence:
            confidence = aggregate_evidence_confidence(all_evidence)
        else:
            confidence = ConfidenceScore(
                value=0.3,
                level=ConfidenceLevel.LOW,
                rationale="Limited evidence available"
            )
        
        # Create mechanism description using actual protein names & gene symbols
        target_descriptions = []
        for t in targets[:5]:  # Top 5 targets
            desc = t.name
            if t.gene_symbol:
                desc = f"{t.name} ({t.gene_symbol})"
            if t.activity and t.activity != 'Unknown':
                desc += f" [{t.activity}]"
            target_descriptions.append(desc)
        
        mechanism_desc = f"{drug_name} acts on {', '.join(target_descriptions)}"
        if pathways:
            pathway_names = [p.name for p in pathways[:3]]
            mechanism_desc += f", affecting pathways: {', '.join(pathway_names)}"
        
        moa_chain = MOAChain(
            drug=drug_name,
            targets=targets,
            pathways=pathways,
            mechanism_description=mechanism_desc,
            confidence=confidence,
            evidence=all_evidence
        )
        
        moa_chains.append(moa_chain)
        
        return moa_chains
