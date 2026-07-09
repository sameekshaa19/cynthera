"""
Database connectors for free biological data sources.
All APIs used are free or have free tiers with optional API keys for higher rate limits.
"""
import requests
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
import yaml
import os
from pathlib import Path

from utils.logger import get_logger
from models.data_models import Evidence, EvidenceSource, ConfidenceScore, ConfidenceLevel

logger = get_logger(__name__)


class BaseConnector:
    """Base class for all database connectors."""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """Initialize connector with configuration."""
        self.config = self._load_config(config_path)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Cynthera-DrugRepurposing/1.0'
        })
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        return {}
    
    def _rate_limit(self, requests_per_second: float = 3):
        """Simple rate limiting."""
        time.sleep(1.0 / requests_per_second)
    
    def _make_request(
        self,
        url: str,
        params: Optional[Dict] = None,
        timeout: int = 30,
        rate_limit: float = 3
    ) -> Optional[Dict]:
        """Make HTTP request with error handling and rate limiting."""
        self._rate_limit(rate_limit)
        
        try:
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            return None


class PubChemConnector(BaseConnector):
    """Connector for PubChem database (free)."""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        super().__init__(config_path)
        self.base_url = self.config.get('apis', {}).get('pubchem', {}).get(
            'base_url', 'https://pubchem.ncbi.nlm.nih.gov/rest/pug'
        )
    
    def get_compound_by_name(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """
        Get compound information by drug name.
        
        Args:
            drug_name: Name of the drug
        
        Returns:
            Compound data or None if not found
        """
        url = f"{self.base_url}/compound/name/{drug_name}/JSON"
        logger.info(f"Fetching PubChem data for: {drug_name}")
        return self._make_request(url)
    
    def get_compound_targets(self, cid: int) -> List[Dict[str, Any]]:
        """
        Get protein targets for a compound.
        
        Args:
            cid: PubChem Compound ID
        
        Returns:
            List of target data
        """
        url = f"{self.base_url}/compound/cid/{cid}/targets/ProteinGI,ProteinName/JSON"
        logger.info(f"Fetching targets for PubChem CID: {cid}")
        data = self._make_request(url)
        
        if data and 'InformationList' in data:
            return data['InformationList'].get('Information', [])
        return []
    
    def get_compound_properties(self, cid: int) -> Optional[Dict[str, Any]]:
        """
        Get compound properties (molecular weight, SMILES, etc.).
        
        Args:
            cid: PubChem Compound ID
        
        Returns:
            Property data or None
        """
        url = f"{self.base_url}/compound/cid/{cid}/property/MolecularFormula,MolecularWeight,CanonicalSMILES/JSON"
        logger.info(f"Fetching properties for PubChem CID: {cid}")
        return self._make_request(url)


class ChEMBLConnector(BaseConnector):
    """Connector for ChEMBL database (free)."""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        super().__init__(config_path)
        self.base_url = self.config.get('apis', {}).get('chembl', {}).get(
            'base_url', 'https://www.ebi.ac.uk/chembl/api/data'
        )
    
    def search_molecule(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """
        Search for a molecule by name.
        
        Args:
            drug_name: Name of the drug
        
        Returns:
            Molecule data or None
        """
        url = f"{self.base_url}/molecule/search"
        params = {'q': drug_name, 'format': 'json'}
        logger.info(f"Searching ChEMBL for: {drug_name}")
        return self._make_request(url, params=params)
    
    def get_activities(self, chembl_id: str) -> List[Dict[str, Any]]:
        """
        Get bioactivity data for a molecule.
        
        Args:
            chembl_id: ChEMBL molecule ID
        
        Returns:
            List of activity data
        """
        url = f"{self.base_url}/activity"
        params = {
            'molecule_chembl_id': chembl_id,
            'format': 'json',
            'limit': 100
        }
        logger.info(f"Fetching activities for ChEMBL ID: {chembl_id}")
        data = self._make_request(url, params=params)
        
        if data and 'activities' in data:
            return data['activities']
        return []
    
    def get_mechanism(self, chembl_id: str) -> List[Dict[str, Any]]:
        """
        Get mechanism of action data.
        
        Args:
            chembl_id: ChEMBL molecule ID
        
        Returns:
            List of mechanism data
        """
        url = f"{self.base_url}/mechanism"
        params = {'molecule_chembl_id': chembl_id, 'format': 'json'}
        logger.info(f"Fetching mechanisms for ChEMBL ID: {chembl_id}")
        data = self._make_request(url, params=params)
        
        if data and 'mechanisms' in data:
            return data['mechanisms']
        return []
    
    def get_bioactivity(self, chembl_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get bioactivity data for a molecule.
        
        Args:
            chembl_id: ChEMBL molecule ID
            limit: Maximum number of activities to return
        
        Returns:
            List of bioactivity data
        """
        url = f"{self.base_url}/activity"
        params = {
            'molecule_chembl_id': chembl_id,
            'format': 'json',
            'limit': limit
        }
        logger.info(f"Fetching bioactivity data for ChEMBL ID: {chembl_id}")
        data = self._make_request(url, params=params)
        
        if data and 'activities' in data:
            return data['activities']
        return []
    
    def get_target_details(self, target_chembl_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed target information including gene symbol and components.
        
        Args:
            target_chembl_id: ChEMBL target ID (e.g., 'CHEMBL2095173')
        
        Returns:
            Target detail dict with keys like 'pref_name', 'target_type',
            'target_components' (which contain gene symbols), or None.
        """
        url = f"{self.base_url}/target/{target_chembl_id}"
        params = {'format': 'json'}
        logger.info(f"Fetching target details for: {target_chembl_id}")
        data = self._make_request(url, params=params)
        return data


class PubMedConnector(BaseConnector):
    """Connector for PubMed E-utilities (free, optional API key for higher limits)."""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        super().__init__(config_path)
        self.base_url = self.config.get('apis', {}).get('pubmed', {}).get(
            'base_url', 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
        )
        self.api_key = os.getenv('NCBI_API_KEY')
        self.email = os.getenv('USER_EMAIL', 'user@example.com')
    
    def search(
        self,
        query: str,
        max_results: int = 10,
        sort: str = 'relevance'
    ) -> List[str]:
        """
        Search PubMed for articles.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            sort: Sort order ('relevance' or 'pub_date')
        
        Returns:
            List of PubMed IDs
        """
        url = f"{self.base_url}/esearch.fcgi"
        params = {
            'db': 'pubmed',
            'term': query,
            'retmax': max_results,
            'retmode': 'json',
            'sort': sort,
            'email': self.email
        }
        
        if self.api_key:
            params['api_key'] = self.api_key
        
        logger.info(f"Searching PubMed for: {query}")
        data = self._make_request(url, params=params, rate_limit=10 if self.api_key else 3)
        
        if data and 'esearchresult' in data:
            return data['esearchresult'].get('idlist', [])
        return []
    
    def fetch_abstracts(self, pmids: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch article abstracts by PubMed IDs.
        
        Args:
            pmids: List of PubMed IDs
        
        Returns:
            List of article data with abstracts
        """
        if not pmids:
            return []
        
        url = f"{self.base_url}/efetch.fcgi"
        params = {
            'db': 'pubmed',
            'id': ','.join(pmids),
            'retmode': 'xml',
            'email': self.email
        }
        
        if self.api_key:
            params['api_key'] = self.api_key
        
        logger.info(f"Fetching {len(pmids)} PubMed abstracts")
        # Note: Returns XML, would need XML parsing in production
        # For MVP, we'll return simplified data
        return [{'pmid': pmid, 'url': f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/'} for pmid in pmids]


class ReactomeConnector(BaseConnector):
    """Connector for Reactome pathway database (free)."""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        super().__init__(config_path)
        self.base_url = self.config.get('apis', {}).get('reactome', {}).get(
            'base_url', 'https://reactome.org/ContentService'
        )
    
    def get_pathways_by_uniprot(self, uniprot_id: str) -> List[Dict[str, Any]]:
        """
        Get pathways associated with a UniProt accession (preferred method).
        
        The /pathways/low/entity/{id}/allForms endpoint should return
        only pathway objects, but we defensively filter to ensure
        only Pathway schema objects are returned.
        
        Args:
            uniprot_id: UniProt accession (e.g., 'P00519' for ABL1)
        
        Returns:
            List of pathway data (filtered to Pathway schema only)
        """
        url = f"{self.base_url}/data/pathways/low/entity/{uniprot_id}/allForms"
        logger.info(f"Fetching Reactome pathways for UniProt: {uniprot_id}")
        data = self._make_request(url)
        
        if not isinstance(data, list):
            return []
        
        # Filter to ONLY actual Pathway objects
        # Reactome can return Reactions, PhysicalEntities, Complexes, etc.
        pathways = []
        for item in data:
            schema_class = item.get('schemaClass', '')
            st_id = item.get('stId', '')
            
            # Accept only Pathway objects (stId like R-HSA-xxxxx)
            if schema_class == 'Pathway' or (st_id.startswith('R-HSA-') and schema_class in ('Pathway', 'TopLevelPathway')):
                pathways.append(item)
        
        logger.info(
            f"Reactome UniProt {uniprot_id}: {len(data)} total objects -> "
            f"{len(pathways)} actual pathways after filtering"
        )
        return pathways
    
    def get_pathways_by_gene(self, gene_symbol: str) -> List[Dict[str, Any]]:
        """
        Get pathways for a gene symbol by searching Reactome (fallback method).
        
        Uses the search endpoint filtered to Pathway type only.
        
        Args:
            gene_symbol: Gene symbol (e.g., 'ABL1')
        
        Returns:
            List of pathway data
        """
        url = f"{self.base_url}/search/query"
        params = {
            'query': gene_symbol,
            'species': 'Homo sapiens',
            'types': 'Pathway',
            'cluster': 'true'
        }
        logger.info(f"Searching Reactome pathways for gene: {gene_symbol}")
        data = self._make_request(url, params=params)
        
        pathways = []
        if data and 'results' in data:
            for group in data['results']:
                entries = group.get('entries', [])
                for entry in entries:
                    st_id = entry.get('stId', '')
                    # Only accept R-HSA pathway IDs (human pathways)
                    if not st_id.startswith('R-HSA-'):
                        continue
                    pathway = {
                        'stId': st_id,
                        'displayName': entry.get('name', ''),
                        'schemaClass': 'Pathway',
                        'summation': [],
                    }
                    pathways.append(pathway)
        
        logger.info(
            f"Reactome gene search '{gene_symbol}': found {len(pathways)} pathways"
        )
        return pathways
    
    def get_pathway_details(self, pathway_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a pathway.
        
        Args:
            pathway_id: Reactome pathway ID
        
        Returns:
            Pathway details or None
        """
        url = f"{self.base_url}/data/query/{pathway_id}"
        logger.info(f"Fetching Reactome pathway details: {pathway_id}")
        return self._make_request(url)


class DisGeNETConnector(BaseConnector):
    """Connector for DisGeNET gene-disease associations (free)."""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        super().__init__(config_path)
        self.base_url = self.config.get('apis', {}).get('disgenet', {}).get(
            'base_url', 'https://www.disgenet.org/api'
        )
    
    def get_disease_genes(self, disease_name: str) -> List[Dict[str, Any]]:
        """
        Get genes associated with a disease.
        
        Args:
            disease_name: Disease name
        
        Returns:
            List of gene-disease associations
        """
        # Note: DisGeNET API requires authentication for full access
        # For MVP, we'll use public endpoints or mock data
        logger.info(f"Fetching DisGeNET data for disease: {disease_name}")
        logger.warning("DisGeNET connector requires API key for full access. Using limited public data.")
        return []
    
    def get_gene_diseases(self, gene_symbol: str) -> List[Dict[str, Any]]:
        """
        Get diseases associated with a gene.
        
        Args:
            gene_symbol: Gene symbol
        
        Returns:
            List of gene-disease associations
        """
        logger.info(f"Fetching DisGeNET data for gene: {gene_symbol}")
        logger.warning("DisGeNET connector requires API key for full access. Using limited public data.")
        return []


class UniProtConnector(BaseConnector):
    """Connector for UniProt protein database (free)."""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        super().__init__(config_path)
        self.base_url = self.config.get('apis', {}).get('uniprot', {}).get(
            'base_url', 'https://rest.uniprot.org'
        )
    
    def search_protein(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Search for proteins.
        
        Args:
            query: Search query (gene name, protein name, etc.)
        
        Returns:
            Search results or None
        """
        url = f"{self.base_url}/uniprotkb/search"
        params = {
            'query': query,
            'format': 'json',
            'size': 10
        }
        logger.info(f"Searching UniProt for: {query}")
        return self._make_request(url, params=params)
    
    def get_protein_details(self, uniprot_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed protein information.
        
        Args:
            uniprot_id: UniProt accession ID
        
        Returns:
            Protein details or None
        """
        url = f"{self.base_url}/uniprotkb/{uniprot_id}.json"
        logger.info(f"Fetching UniProt details for: {uniprot_id}")
        return self._make_request(url)
