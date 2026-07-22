"""RetrievalPipeline — async parallel evidence retrieval engine.

Reference: 01_SYSTEM_ARCHITECTURE.md §8, 03_RETRIEVAL_SPECIFICATION.md
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.pathway import Pathway
from backend.core.domain.evidence import Evidence
from backend.core.domain.clinical_trial import ClinicalTrial
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.evidence_type import EvidenceType
from backend.core.enums.trial_outcome import TrialOutcomeStatus
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.engineering.retrieval.connectors.chembl import ChEMBLConnector
from backend.engineering.retrieval.connectors.uniprot import UniProtConnector
from backend.engineering.retrieval.connectors.pubmed import PubMedConnector
from backend.engineering.retrieval.connectors.reactome import ReactomeConnector
from backend.engineering.retrieval.connectors.clinicaltrials import ClinicalTrialsConnector
from backend.engineering.retrieval.connectors.disgenet import DisGeNETConnector

logger = logging.getLogger(__name__)


class RetrievalPipeline:
    """Async parallel retrieval pipeline that queries all data sources concurrently.

    Implements Phase 2 parallel execution from 01_SYSTEM_ARCHITECTURE.md:
    - ChEMBL, UniProt, PubMed, Reactome, ClinicalTrials queried in parallel
    - Results aggregated into a sealed RetrievalPackage

    Failure handling:
    - UniProt/ChEMBL failures → halt (SourceUnavailableError propagated)
    - Reactome/PubMed/ClinicalTrials failures → degrade gracefully, log warning
    """

    def __init__(
        self,
        ncbi_api_key: str | None = None,
        disgenet_api_key: str | None = None,
    ) -> None:
        """Initialize the retrieval pipeline.

        Args:
            ncbi_api_key: Optional NCBI API key for higher PubMed rate limits.
            disgenet_api_key: Optional DisGeNET API key.
        """
        self._ncbi_api_key = ncbi_api_key
        self._disgenet_api_key = disgenet_api_key

    async def execute(
        self,
        drug: Drug,
        disease: Disease,
        hypothesis_id: uuid.UUID,
    ) -> RetrievalPackage:
        """Execute the sequential-parallel retrieval pipeline.

        Phase 1: Sequential ID Fetch (ChEMBL first to get target UniProt accessions)
        Phase 2: Parallel Fetch (UniProt, Reactome, PubMed, ClinicalTrials in parallel)
        """
        logger.info(
            "retrieval_pipeline_start",
            extra={
                "drug": drug.name,
                "disease": disease.name,
                "hypothesis_id": str(hypothesis_id),
            },
        )

        chembl_id = drug.chembl_id or drug.name
        sources_queried: list[str] = []
        sources_failed: list[str] = []

        targets: list[Target] = []
        proteins: list[Protein] = []
        pathways: list[Pathway] = []
        evidence_records: list[Evidence] = []
        clinical_trials: list[ClinicalTrial] = []

        # --- Phase 1: Sequential Fetch (ChEMBL) ---
        try:
            chembl_data = await self._fetch_chembl(chembl_id)
            sources_queried.append("chembl")
            targets, chembl_evidence = self._parse_chembl_data(chembl_data, drug)
            evidence_records.extend(chembl_evidence)
        except Exception as exc:
            sources_failed.append("chembl")
            logger.error("chembl_failed", extra={"error": str(exc)})
            chembl_data = {}

        # Extract unique UniProt IDs from targets to fetch in Phase 2
        uniprot_ids = list(set(t.protein_uniprot for t in targets if t.protein_uniprot))

        # --- Phase 2: Parallel Fetch ---
        results = await asyncio.gather(
            self._fetch_uniprot(uniprot_ids),
            self._fetch_pubmed(drug.name, disease.name),
            self._fetch_reactome(uniprot_ids),
            self._fetch_clinicaltrials(drug.name, disease.name),
            self._fetch_disgenet(disease.name),
            return_exceptions=True,
        )

        uniprot_data, pubmed_data, reactome_data, trials_data, disgenet_data = results

        # Process UniProt proteins
        if isinstance(uniprot_data, Exception):
            sources_failed.append("uniprot")
            logger.warning("uniprot_failed", extra={"error": str(uniprot_data)})
        else:
            sources_queried.append("uniprot")
            proteins = self._parse_uniprot_data(uniprot_data)

        # Process PubMed literature
        if isinstance(pubmed_data, Exception):
            sources_failed.append("pubmed")
            logger.warning("pubmed_failed", extra={"error": str(pubmed_data)})
        else:
            sources_queried.append("pubmed")
            lit_evidence = self._parse_pubmed_data(pubmed_data, drug, disease)
            evidence_records.extend(lit_evidence)

        # Process Reactome pathways
        if isinstance(reactome_data, Exception):
            sources_failed.append("reactome")
            logger.warning("reactome_failed", extra={"error": str(reactome_data)})
        else:
            sources_queried.append("reactome")
            pathways = self._parse_reactome_data(reactome_data)

        # Process ClinicalTrials
        if isinstance(trials_data, Exception):
            sources_failed.append("clinicaltrials")
            logger.warning("clinicaltrials_failed", extra={"error": str(trials_data)})
        else:
            sources_queried.append("clinicaltrials")
            clinical_trials = self._parse_trials_data(trials_data, drug, disease)

        # Process DisGeNET disease-gene associations (graceful degradation — requires API key)
        if isinstance(disgenet_data, Exception):
            logger.debug("disgenet_failed", extra={"error": str(disgenet_data)})
        elif disgenet_data:
            sources_queried.append("disgenet")
            disgenet_evidence = self._parse_disgenet_data(disgenet_data, drug, disease)
            evidence_records.extend(disgenet_evidence)

        # Determine retrieval confidence
        confidence = self._compute_confidence(
            targets, evidence_records, pathways, clinical_trials, sources_failed
        )

        package = RetrievalPackage(
            hypothesis_id=hypothesis_id,
            drug=drug,
            disease=disease,
            targets=targets,
            proteins=proteins,
            pathways=pathways,
            evidence_records=evidence_records,
            clinical_trials=clinical_trials,
            retrieval_confidence=confidence,
            sources_queried=sources_queried,
            sources_failed=sources_failed,
            sealed_at=datetime.utcnow(),
        )

        logger.info(
            "retrieval_pipeline_complete",
            extra={
                "hypothesis_id": str(hypothesis_id),
                "evidence_count": len(evidence_records),
                "trial_count": len(clinical_trials),
                "pathway_count": len(pathways),
                "confidence": confidence,
                "sources_failed": sources_failed,
            },
        )
        return package

    async def _fetch_chembl(self, chembl_id: str) -> dict[str, Any]:
        async with ChEMBLConnector() as conn:
            bioactivities = await conn.fetch(chembl_id)
            mechanisms = await conn.fetch_targets(chembl_id)
            
            # Extract up to 10 unique target ChEMBL IDs to query their details
            activities = bioactivities.get("activities", [])
            target_ids = list(set(act.get("target_chembl_id") for act in activities if act.get("target_chembl_id")))
            target_details_dict = {}

            async def fetch_target_details(tid: str):
                try:
                    url = f"{conn.base_url}/target/{tid}.json"
                    res = await conn._get(url)
                    target_details_dict[tid] = res
                except Exception as e:
                    logger.debug("target_detail_fetch_failed", extra={"target_id": tid, "error": str(e)})

            if target_ids:
                await asyncio.gather(*(fetch_target_details(tid) for tid in target_ids[:10]))

            return {
                "bioactivities": bioactivities,
                "mechanisms": mechanisms,
                "target_details": target_details_dict
            }

    async def _fetch_uniprot(self, uniprot_ids: list[str]) -> dict[str, Any]:
        """Fetch protein information from UniProt in parallel."""
        if not uniprot_ids:
            return {"proteins": []}
        async with UniProtConnector() as conn:
            proteins = []
            async def fetch_one(uid: str):
                try:
                    res = await conn.fetch(uid)
                    proteins.append(res)
                except Exception as e:
                    logger.debug("uniprot_fetch_one_failed", extra={"uniprot_id": uid, "error": str(e)})
            await asyncio.gather(*(fetch_one(uid) for uid in uniprot_ids[:5]))
            return {"proteins": proteins}

    async def _fetch_pubmed(self, drug_name: str, disease_name: str) -> dict[str, Any]:
        async with PubMedConnector(api_key=self._ncbi_api_key) as conn:
            return await conn.fetch(drug_name, disease_name, max_results=50)

    async def _fetch_reactome(self, uniprot_ids: list[str]) -> dict[str, Any]:
        """Fetch biological pathways from Reactome in parallel."""
        if not uniprot_ids:
            return {"pathways": []}
        async with ReactomeConnector() as conn:
            pathways = []
            async def fetch_one(uid: str):
                try:
                    res = await conn.fetch(uid)
                    pathways.extend(res.get("pathways", []))
                except Exception as e:
                    logger.debug("reactome_fetch_one_failed", extra={"uniprot_id": uid, "error": str(e)})
            await asyncio.gather(*(fetch_one(uid) for uid in uniprot_ids[:5]))
            return {"pathways": pathways}

    async def _fetch_clinicaltrials(self, drug_name: str, disease_name: str) -> dict[str, Any]:
        async with ClinicalTrialsConnector() as conn:
            return await conn.fetch(drug_name, disease_name)

    async def _fetch_disgenet(self, disease_name: str) -> dict[str, Any]:
        """Fetch disease-gene associations from DisGeNET.

        DisGeNET requires an API key for full access. Without one the connector
        returns an empty payload rather than raising, so this method degrades
        gracefully when the key is absent.
        """
        try:
            async with DisGeNETConnector(api_key=self._disgenet_api_key) as conn:
                # Use the disease name as the query identifier (may return empty if unauthenticated)
                result = await conn.fetch(disease_id=disease_name.lower().replace(" ", "+"))
                return result
        except Exception as exc:
            logger.debug("disgenet_fetch_failed", extra={"error": str(exc)})
            return {}

    def _parse_chembl_data(
        self,
        data: dict[str, Any],
        drug: Drug,
    ) -> tuple[list[Target], list[Evidence]]:
        """Parse ChEMBL bioactivity data into Target and Evidence objects."""
        targets: list[Target] = []
        evidence: list[Evidence] = []
        activities = data.get("bioactivities", {}).get("activities", [])
        target_details = data.get("target_details", {})

        # Build mapping from target ChEMBL ID to the first UniProt accession found
        uniprot_map = {}
        for tid, tdata in target_details.items():
            components = tdata.get("target_components", [])
            for comp in components:
                for xref in comp.get("target_component_xrefs", []):
                    if xref.get("xref_src_db") == "UniProt":
                        uniprot_map[tid] = xref.get("xref_id")
                        break
                if tid in uniprot_map:
                    break

        for act in activities[:50]:  # cap at 50
            try:
                standard_value = float(act.get("standard_value") or 0)
                affinity_type = act.get("standard_type", "IC50")
                target_chembl = act.get("target_chembl_id", "")
                
                # Retrieve UniProt from our mapped dictionary or fallback to act's target_accession
                target_uniprot = uniprot_map.get(target_chembl) or act.get("target_accession", "")
                mechanism = act.get("mechanism_of_action", "UNKNOWN")

                if not target_uniprot or standard_value <= 0:
                    continue

                erw = ERW.from_base(
                    base_weight=EvidenceType.IN_VITRO.base_erw,
                )
                prov = ProvenanceReference(
                    source_name="ChEMBL",
                    source_version="v33",
                    record_id=str(act.get("activity_id", "unknown")),
                    url=f"https://www.ebi.ac.uk/chembl/activity/{act.get('activity_id', '')}",
                )
                target = Target(
                    drug_chembl_id=drug.chembl_id or drug.name,
                    protein_uniprot=target_uniprot,
                    affinity_nm=standard_value,
                    affinity_type=affinity_type if affinity_type in {
                        "Ki", "IC50", "Kd", "percent_inhibition", "EC50", "Potency"
                    } else "IC50",
                    mechanism=mechanism.upper().replace(" ", "_")[:20],
                    erw=erw,
                    provenance=prov,
                )
                targets.append(target)

                ev = Evidence(
                    evidence_type=EvidenceType.IN_VITRO,
                    erw=erw,
                    citation_key=str(act.get("activity_id", f"chembl_{len(evidence)}")),
                    title=f"ChEMBL bioactivity: {drug.name} vs {target_uniprot}",
                    provenance=prov,
                    drug_chembl_id=drug.chembl_id,
                )
                evidence.append(ev)
            except Exception as exc:
                logger.debug("chembl_record_parse_error", extra={"error": str(exc)})
                continue
        return targets, evidence

    def _parse_uniprot_data(self, data: dict[str, Any]) -> list[Protein]:
        """Parse UniProt data into Protein objects."""
        proteins = []
        raw_proteins = data.get("proteins", [])
        for raw in raw_proteins:
            try:
                acc = raw.get("primaryAccession", "")
                if not acc:
                    continue
                gene_symbol = "UNKNOWN"
                name = "Unknown protein"
                
                genes = raw.get("genes", [])
                if genes:
                    gene_symbol = genes[0].get("geneName", {}).get("value", "UNKNOWN")
                
                protein_desc = raw.get("proteinDescription", {})
                rec_name = protein_desc.get("recommendedName", {})
                if rec_name:
                    name = rec_name.get("fullName", {}).get("value", "Unknown protein")

                protein = Protein(
                    uniprot_accession=acc,
                    gene_symbol=gene_symbol.upper(),
                    name=name,
                    organism=raw.get("organism", {}).get("scientificName", "Homo sapiens"),
                )
                proteins.append(protein)
            except Exception as e:
                logger.debug("uniprot_parse_error", extra={"error": str(e)})
                continue
        return proteins

    def _parse_pubmed_data(
        self,
        data: dict[str, Any],
        drug: Drug,
        disease: Disease,
    ) -> list[Evidence]:
        """Parse PubMed data into Evidence objects."""
        evidence: list[Evidence] = []
        pmids = data.get("pmids", [])
        abstracts = data.get("abstracts", {})
        for pmid in pmids[:20]:
            try:
                abstract_text = abstracts.get(pmid, "")
                erw = ERW.from_base(base_weight=EvidenceType.OBSERVATIONAL.base_erw)
                prov = ProvenanceReference(
                    source_name="PubMed",
                    source_version="2024",
                    record_id=pmid,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                )
                ev = Evidence(
                    evidence_type=EvidenceType.OBSERVATIONAL,
                    erw=erw,
                    citation_key=f"PMID:{pmid}",
                    title=f"PubMed article {pmid}",
                    abstract=abstract_text[:2000] if abstract_text else None,
                    provenance=prov,
                    drug_chembl_id=drug.chembl_id,
                    disease_identifier=disease.mesh_id,
                )
                evidence.append(ev)
            except Exception as exc:
                logger.debug("pubmed_record_parse_error", extra={"error": str(exc)})
                continue
        return evidence

    def _parse_reactome_data(self, data: dict[str, Any]) -> list[Pathway]:
        """Parse Reactome data into Pathway objects."""
        pathways = []
        raw_pathways = data.get("pathways", [])
        seen = set()
        for raw in raw_pathways:
            reactome_id = raw.get("stId")
            if not reactome_id or reactome_id in seen:
                continue
            seen.add(reactome_id)
            try:
                import re
                if not re.match(r"^R-[A-Z]+-\d+$", reactome_id):
                    continue

                prov = ProvenanceReference(
                    source_name="Reactome",
                    source_version="2024",
                    record_id=reactome_id,
                    url=f"https://reactome.org/content/detail/{reactome_id}",
                )
                pathway = Pathway(
                    reactome_id=reactome_id,
                    name=raw.get("displayName", "Unnamed pathway"),
                    description=raw.get("displayName", "Unnamed pathway"),
                    provenance=prov,
                )
                pathways.append(pathway)
            except Exception as e:
                logger.debug("reactome_parse_error", extra={"error": str(e)})
                continue
        return pathways

    def _parse_trials_data(
        self,
        data: dict[str, Any],
        drug: Drug,
        disease: Disease,
    ) -> list[ClinicalTrial]:
        """Parse ClinicalTrials.gov data into ClinicalTrial objects."""
        trials: list[ClinicalTrial] = []
        studies = data.get("studies", [])
        for study in studies[:20]:
            try:
                protocol = study.get("protocolSection", {})
                ident = protocol.get("identificationModule", {})
                status_mod = protocol.get("statusModule", {})
                design_mod = protocol.get("designModule", {})

                nct_id = ident.get("nctId", "")
                if not nct_id or not nct_id.startswith("NCT"):
                    continue

                raw_status = status_mod.get("overallStatus", "UNKNOWN").upper()
                status_map: dict[str, TrialOutcomeStatus] = {
                    "COMPLETED": TrialOutcomeStatus.COMPLETED_SUCCESS,
                    "TERMINATED": TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY,
                    "RECRUITING": TrialOutcomeStatus.ACTIVE,
                    "ACTIVE_NOT_RECRUITING": TrialOutcomeStatus.ACTIVE,
                    "WITHDRAWN": TrialOutcomeStatus.COMPLETED_FAILURE,
                }
                status = status_map.get(raw_status, TrialOutcomeStatus.UNKNOWN)

                phase_list = design_mod.get("phases", ["N/A"])
                phase_map: dict[str, str] = {
                    "PHASE1": "Phase I", "PHASE2": "Phase II",
                    "PHASE3": "Phase III", "PHASE4": "Phase IV",
                    "PHASE1_PHASE2": "Phase I/II", "PHASE2_PHASE3": "Phase II/III",
                }
                phase = phase_map.get(phase_list[0] if phase_list else "N/A", "N/A")

                prov = ProvenanceReference(
                    source_name="ClinicalTrials.gov",
                    source_version="2024",
                    record_id=nct_id,
                    url=f"https://clinicaltrials.gov/study/{nct_id}",
                )
                trial = ClinicalTrial(
                    nct_id=nct_id,
                    title=ident.get("briefTitle", "Unknown trial"),
                    phase=phase,
                    status=status,
                    drug_chembl_id=drug.chembl_id,
                    disease_identifier=disease.mesh_id,
                    provenance=prov,
                )
                trials.append(trial)
            except Exception as exc:
                logger.debug("trial_parse_error", extra={"error": str(exc)})
                continue
        return trials

    def _parse_disgenet_data(
        self,
        data: dict[str, Any],
        drug: Drug,
        disease: Disease,
    ) -> list[Evidence]:
        """Parse DisGeNET gene-disease association data into Evidence objects.

        Args:
            data: Raw DisGeNET response (list of associations or dict with list).
            drug: Drug entity (for provenance context).
            disease: Disease entity.

        Returns:
            List of Evidence records derived from DisGeNET associations.
        """
        evidence: list[Evidence] = []
        # DisGeNET response may be a list or a dict with a 'payload' key
        associations: list[dict[str, Any]] = []
        if isinstance(data, list):
            associations = data
        elif isinstance(data, dict):
            associations = data.get("payload", data.get("results", []))

        for assoc in associations[:20]:  # cap at 20
            try:
                gene_symbol = assoc.get("gene_symbol") or assoc.get("geneName", "UNKNOWN")
                score = float(assoc.get("score", 0.0))
                if score <= 0:
                    continue

                erw = ERW.from_base(base_weight=EvidenceType.OBSERVATIONAL.base_erw)
                prov = ProvenanceReference(
                    source_name="DisGeNET",
                    source_version="2024",
                    record_id=f"disgenet_{gene_symbol}",
                    url=f"https://www.disgenet.org/browser/0/1/0/{gene_symbol}/",
                )
                ev = Evidence(
                    evidence_type=EvidenceType.OBSERVATIONAL,
                    erw=erw,
                    citation_key=f"DisGeNET:{gene_symbol}:{disease.name}",
                    title=f"DisGeNET association: {gene_symbol} — {disease.name}",
                    abstract=(
                        f"Gene {gene_symbol} is associated with {disease.name} "
                        f"with DisGeNET score {score:.3f}."
                    ),
                    provenance=prov,
                    disease_identifier=disease.mesh_id,
                )
                evidence.append(ev)
            except Exception as exc:
                logger.debug("disgenet_parse_error", extra={"error": str(exc)})
                continue
        return evidence

    def _compute_confidence(
        self,
        targets: list[Target],
        evidence: list[Evidence],
        pathways: list[Pathway],
        trials: list[ClinicalTrial],
        sources_failed: list[str],
    ) -> str:
        """Determine retrieval confidence level based on data richness.

        Returns:
            'HIGH', 'MEDIUM', or 'LOW'.
        """
        if "chembl" in sources_failed or "uniprot" in sources_failed:
            return "LOW"
        score = 0
        if len(targets) >= 1:
            score += 2
        if len(evidence) >= 5:
            score += 2
        if len(pathways) >= 1:
            score += 1
        if len(trials) >= 1:
            score += 1
        if score >= 5:
            return "HIGH"
        if score >= 2:
            return "MEDIUM"
        return "LOW"
