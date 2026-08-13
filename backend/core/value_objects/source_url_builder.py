"""SourceURLBuilder — constructs canonical, clickable source URLs for biomedical entities and literature.

Reference: Evidence Traceability requirement. Never fabricates URLs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceLink:
    """A verified, clickable URL link for an evidence record or database entity.

    Attributes:
        source_name: Human-readable name of the source (e.g., 'PubMed', 'ChEMBL').
        display_label: Action label for UI buttons (e.g., 'Open PubMed', 'Open ChEMBL').
        url: Canonical target URL string.
        entity_id: The raw accession or citation key.
        link_type: 'paper' | 'database' | 'full_text' | 'trial'.
    """

    source_name: str
    display_label: str
    url: str
    entity_id: str
    link_type: str = "database"

    def to_dict(self) -> dict[str, str]:
        return {
            "source_name": self.source_name,
            "display_label": self.display_label,
            "url": self.url,
            "entity_id": self.entity_id,
            "link_type": self.link_type,
        }


class SourceURLBuilder:
    """Builds canonical URLs for biomedical entities and publications."""

    @staticmethod
    def pubmed_url(pmid: str) -> str | None:
        clean = pmid.replace("PMID:", "").strip()
        if clean and clean.isdigit():
            return f"https://pubmed.ncbi.nlm.nih.gov/{clean}/"
        return None

    @staticmethod
    def doi_url(doi: str) -> str | None:
        clean = doi.replace("doi:", "").replace("DOI:", "").strip()
        if clean and clean.startswith("10."):
            return f"https://doi.org/{clean}"
        return None

    @staticmethod
    def europepmc_url(pmid: str | None = None, doi: str | None = None) -> str | None:
        if pmid:
            clean_pmid = pmid.replace("PMID:", "").strip()
            if clean_pmid.isdigit():
                return f"https://europepmc.org/article/MED/{clean_pmid}"
        if doi:
            clean_doi = doi.replace("doi:", "").replace("DOI:", "").strip()
            if clean_doi.startswith("10."):
                return f"https://europepmc.org/search?query=DOI:{clean_doi}"
        return None

    @staticmethod
    def chembl_compound_url(chembl_id: str) -> str | None:
        clean = chembl_id.strip().upper()
        if clean.startswith("CHEMBL"):
            return f"https://www.ebi.ac.uk/chembl/compound_report_card/{clean}/"
        return None

    @staticmethod
    def chembl_target_url(chembl_id: str) -> str | None:
        clean = chembl_id.strip().upper()
        if clean.startswith("CHEMBL"):
            return f"https://www.ebi.ac.uk/chembl/target_report_card/{clean}/"
        return None

    @staticmethod
    def uniprot_url(accession: str) -> str | None:
        clean = accession.split("-")[0].strip().upper()
        if clean and len(clean) >= 6:
            return f"https://www.uniprot.org/uniprotkb/{clean}/entry"
        return None

    @staticmethod
    def reactome_url(reactome_id: str) -> str | None:
        clean = reactome_id.strip().upper()
        if clean.startswith("R-"):
            return f"https://reactome.org/content/detail/{clean}"
        return None

    @staticmethod
    def opentargets_disease_url(disease_id: str) -> str | None:
        clean = disease_id.strip()
        if clean:
            if clean.startswith("EFO_") or clean.startswith("MONDO_") or clean.startswith("DOID_"):
                return f"https://platform.opentargets.org/disease/{clean}"
            return f"https://platform.opentargets.org/search?q={clean}"
        return None

    @staticmethod
    def opentargets_target_url(gene_symbol_or_ensembl: str) -> str | None:
        clean = gene_symbol_or_ensembl.strip().upper()
        if clean:
            return f"https://platform.opentargets.org/target/{clean}"
        return None

    @staticmethod
    def disgenet_url(gene_symbol: str) -> str | None:
        clean = gene_symbol.strip().upper()
        if clean:
            return f"https://www.disgenet.org/browser/0/1/0/{clean}/"
        return None

    @staticmethod
    def clinicaltrials_url(nct_id: str) -> str | None:
        clean = nct_id.strip().upper()
        if clean.startswith("NCT"):
            return f"https://clinicaltrials.gov/study/{clean}"
        return None

    @classmethod
    def build_links_for_citation_key(cls, citation_key: str, title: str | None = None) -> list[EvidenceLink]:
        """Build all valid EvidenceLinks for a given citation key (PMID, DOI, NCT, etc.)."""
        links: list[EvidenceLink] = []
        key = citation_key.strip()

        # Check PMID
        if key.startswith("PMID:") or key.isdigit():
            pmid = key.replace("PMID:", "").strip()
            pm_url = cls.pubmed_url(pmid)
            if pm_url:
                links.append(EvidenceLink(
                    source_name="PubMed",
                    display_label="Open PubMed",
                    url=pm_url,
                    entity_id=f"PMID:{pmid}",
                    link_type="paper",
                ))
            epmc_url = cls.europepmc_url(pmid=pmid)
            if epmc_url:
                links.append(EvidenceLink(
                    source_name="Europe PMC",
                    display_label="Open Europe PMC",
                    url=epmc_url,
                    entity_id=f"PMID:{pmid}",
                    link_type="paper",
                ))

        # Check DOI
        if key.startswith("doi:") or key.startswith("DOI:") or key.startswith("10."):
            doi = key.replace("doi:", "").replace("DOI:", "").strip()
            doi_u = cls.doi_url(doi)
            if doi_u:
                links.append(EvidenceLink(
                    source_name="DOI",
                    display_label="Open DOI",
                    url=doi_u,
                    entity_id=f"DOI:{doi}",
                    link_type="paper",
                ))

        # Check NCT
        if key.startswith("NCT"):
            ct_u = cls.clinicaltrials_url(key)
            if ct_u:
                links.append(EvidenceLink(
                    source_name="ClinicalTrials.gov",
                    display_label="Open ClinicalTrials",
                    url=ct_u,
                    entity_id=key,
                    link_type="trial",
                ))

        return links
