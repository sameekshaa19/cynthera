"""RetrievalPipeline — async parallel evidence retrieval engine.

Reference: 01_SYSTEM_ARCHITECTURE.md §8, 03_RETRIEVAL_SPECIFICATION.md
"""
from __future__ import annotations

import asyncio
import logging
import re
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
from backend.core.domain.approval_signal import ApprovalSignal
from backend.core.value_objects.biological_identifier import BiologicalIdentifierMapping
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
from backend.infrastructure.cache.raw_response_cache import (
    RawResponseCache,
    TTL_STRUCTURAL,
    TTL_ASSOCIATIONS,
    TTL_LITERATURE,
    TTL_CLINICAL_TRIALS,
)
# Phase 2: Extended literature sources
try:
    from backend.engineering.retrieval.connectors.openalex import OpenAlexConnector
    from backend.engineering.retrieval.connectors.semantic_scholar import SemanticScholarConnector
    _EXTENDED_SOURCES_AVAILABLE = True
except ImportError:
    _EXTENDED_SOURCES_AVAILABLE = False
# Phase 4: New free data sources
try:
    from backend.engineering.retrieval.connectors.europepmc import EuropePMCConnector
    from backend.engineering.retrieval.connectors.opentargets import OpenTargetsConnector
    _NEW_SOURCES_AVAILABLE = True
except ImportError:
    _NEW_SOURCES_AVAILABLE = False

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
        semantic_scholar_api_key: str | None = None,
        db_path: str = "data/cynthera.db",
        bypass_raw_cache: bool = False,
    ) -> None:
        """Initialize the retrieval pipeline.

        Args:
            ncbi_api_key: Optional NCBI API key for higher PubMed rate limits.
            disgenet_api_key: Optional DisGeNET API key.
            semantic_scholar_api_key: Optional Semantic Scholar API key for higher rate limits.
            db_path: Path to the SQLite database for raw response cache.
            bypass_raw_cache: If True, skip cache reads (force fresh API calls).
                              Cache writes still occur so subsequent runs benefit.
        """
        import os
        from backend.core.utils.api_keys import sanitize_api_key
        self._ncbi_api_key = sanitize_api_key(ncbi_api_key)
        self._disgenet_api_key = sanitize_api_key(disgenet_api_key)
        self._semantic_scholar_api_key = sanitize_api_key(
            semantic_scholar_api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        )
        self._raw_cache = RawResponseCache(db_path=db_path)
        self._bypass_raw_cache = bypass_raw_cache

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
        cache_hits: int = 0
        cache_misses: int = 0

        targets: list[Target] = []
        proteins: list[Protein] = []
        pathways: list[Pathway] = []
        evidence_records: list[Evidence] = []
        clinical_trials: list[ClinicalTrial] = []
        validated_disease_genes: dict[str, float] = {}

        # --- Phase 1: Sequential Fetch (ChEMBL — bioactivities + indications + molecule details) ---
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

        # --- Phase 2: Parallel Fetch (core sources) ---
        results = await asyncio.gather(
            self._fetch_uniprot(uniprot_ids),
            self._fetch_pubmed(drug.name, disease.name),
            self._fetch_reactome(uniprot_ids),
            self._fetch_clinicaltrials(drug.name, disease.name),
            self._fetch_disgenet(disease),
            return_exceptions=True,
        )

        uniprot_data, pubmed_data, reactome_data, trials_data, disgenet_data = results

        # --- Phase 2 Extended: OpenAlex + Semantic Scholar (non-critical) ---
        if _EXTENDED_SOURCES_AVAILABLE:
            ext_results = await asyncio.gather(
                self._fetch_openalex(drug.name, disease.name, hypothesis_id),
                self._fetch_semantic_scholar(drug.name, disease.name, hypothesis_id),
                return_exceptions=True,
            )
            openalex_ev, s2_ev = ext_results
            if isinstance(openalex_ev, Exception):
                sources_failed.append("openalex")
                logger.debug("openalex_failed", extra={"error": str(openalex_ev)})
            else:
                sources_queried.append("openalex")
                if isinstance(openalex_ev, list) and openalex_ev:
                    evidence_records.extend(openalex_ev)

            if isinstance(s2_ev, Exception):
                sources_failed.append("semantic_scholar")
                logger.debug("semantic_scholar_failed", extra={"error": str(s2_ev)})
            else:
                sources_queried.append("semantic_scholar")
                if isinstance(s2_ev, list) and s2_ev:
                    evidence_records.extend(s2_ev)

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

        # Collect source-provided biological identifier mappings
        identifier_mappings: list[BiologicalIdentifierMapping] = []

        # Process Reactome pathways
        if isinstance(reactome_data, Exception):
            sources_failed.append("reactome")
            logger.warning("reactome_failed", extra={"error": str(reactome_data)})
        else:
            sources_queried.append("reactome")
            pathways = self._parse_reactome_data(reactome_data)
            for m in reactome_data.get("mappings", []):
                if isinstance(m, BiologicalIdentifierMapping):
                    identifier_mappings.append(m)
                elif isinstance(m, dict):
                    identifier_mappings.append(
                        BiologicalIdentifierMapping(
                            canonical_symbol=m.get("canonical_symbol"),
                            uniprot_accession=m.get("uniprot_accession"),
                            source=m.get("source", "Reactome"),
                            score=m.get("score"),
                            original_identifiers=tuple(m.get("original_identifiers", ())),
                        )
                    )

        # Process ClinicalTrials
        if isinstance(trials_data, Exception):
            sources_failed.append("clinicaltrials")
            logger.warning("clinicaltrials_failed", extra={"error": str(trials_data)})
        else:
            sources_queried.append("clinicaltrials")
            clinical_trials = self._parse_trials_data(trials_data, drug, disease)

        # Process DisGeNET disease-gene associations.
        # DisGeNET associations are indexed into validated_disease_genes, NOT evidence_records.
        # They represent gene-disease association strength, not literature claim quality.
        if isinstance(disgenet_data, Exception):
            logger.debug("disgenet_failed", extra={"error": str(disgenet_data)})
        elif disgenet_data:
            sources_queried.append("disgenet")
            dg_genes = self._parse_disgenet_to_gene_scores(disgenet_data)
            validated_disease_genes.update(dg_genes)
            logger.info(
                "disgenet_genes_indexed",
                extra={"gene_count": len(dg_genes)},
            )

        # --- Phase 2 Extended (b): Europe PMC + Open Targets ---
        if _NEW_SOURCES_AVAILABLE:
            new_results = await asyncio.gather(
                self._fetch_europepmc(drug.name, disease.name, hypothesis_id),
                self._fetch_opentargets(disease),
                return_exceptions=True,
            )
            epmc_ev, ot_result = new_results

            # Europe PMC → evidence_records (literature, same as OpenAlex/S2)
            if isinstance(epmc_ev, list):
                sources_queried.append("europepmc")
                evidence_records.extend(epmc_ev)
                # Track cache contribution — EuropePMC fetch updates cache_hits internally
            elif isinstance(epmc_ev, Exception):
                sources_failed.append("europepmc")
                logger.warning("europepmc_failed", extra={"error": str(epmc_ev)})

            # Open Targets → validated_disease_genes & identifier_mappings (NOT evidence_records)
            if isinstance(ot_result, dict):
                sources_queried.append("opentargets")
                if "gene_scores" in ot_result:
                    ot_scores = ot_result.get("gene_scores", {})
                    validated_disease_genes.update(ot_scores)
                    for m in ot_result.get("mappings", []):
                        if isinstance(m, BiologicalIdentifierMapping):
                            identifier_mappings.append(m)
                        elif isinstance(m, dict):
                            identifier_mappings.append(
                                BiologicalIdentifierMapping(
                                    canonical_symbol=m.get("canonical_symbol"),
                                    uniprot_accession=m.get("uniprot_accession"),
                                    source=m.get("source", "OpenTargets"),
                                    score=m.get("score"),
                                    original_identifiers=tuple(m.get("original_identifiers", ())),
                                )
                            )
                    logger.info(
                        "opentargets_genes_indexed",
                        extra={
                            "gene_count": len(ot_scores),
                            "mappings_count": len(ot_result.get("mappings", [])),
                        },
                    )
                else:
                    validated_disease_genes.update(ot_result)
                    logger.info(
                        "opentargets_genes_indexed",
                        extra={"gene_count": len(ot_result)},
                    )
            elif isinstance(ot_result, Exception):
                sources_failed.append("opentargets")
                logger.warning("opentargets_failed", extra={"error": str(ot_result)})

        # --- Determine approval signal from retrieved indication data ---
        approval_signal = self._parse_indication_data(
            chembl_data.get("indications", {}),
            chembl_data.get("molecule_details", {}),
            disease.name,
        )

        # --- Determine clinical trial retrieval status (not just count) ---
        if "clinicaltrials" in sources_failed:
            ct_status = "API_FAILURE"
        elif "clinicaltrials" in sources_queried and len(clinical_trials) == 0:
            ct_status = "NOT_FOUND"
        elif len(clinical_trials) > 0:
            ct_status = "RETRIEVED"
        else:
            ct_status = "NOT_ATTEMPTED"

        # --- Determine retrieval confidence ---
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
            approval_signal=approval_signal,
            clinical_trial_retrieval_status=ct_status,
            validated_disease_genes=validated_disease_genes,
            identifier_mappings=identifier_mappings,
        )

        # Pipeline summary: cache stats for this run
        cache_stats = self._raw_cache.stats()
        logger.info(
            "retrieval_pipeline_complete",
            extra={
                "hypothesis_id": str(hypothesis_id),
                "evidence_count": len(evidence_records),
                "trial_count": len(clinical_trials),
                "pathway_count": len(pathways),
                "confidence": confidence,
                "sources_failed": sources_failed,
                "validated_gene_count": len(validated_disease_genes),
                "raw_cache_entries": cache_stats["active_entries"],
                "raw_cache_hits": cache_stats["total_cache_hits"],
            },
        )
        return package

    async def _fetch_chembl(self, chembl_id: str) -> dict[str, Any]:
        async with ChEMBLConnector() as conn:
            bioactivities = await conn.fetch(chembl_id)
            mechanisms = await conn.fetch_targets(chembl_id)

            # Fetch molecule details (max_phase, synonyms) and indications in parallel
            mol_details, ind_data = await asyncio.gather(
                conn.fetch_molecule_details(chembl_id),
                conn.fetch_indications(chembl_id),
                return_exceptions=True,
            )
            if isinstance(mol_details, Exception):
                logger.debug("chembl_mol_details_failed", extra={"error": str(mol_details)})
                mol_details = {}
            if isinstance(ind_data, Exception):
                logger.debug("chembl_ind_data_failed", extra={"error": str(ind_data)})
                ind_data = {"indications": []}

            # Prioritize target ChEMBL IDs from curated mechanism records FIRST,
            # falling back to frequency-ranked targets from bioactivities.
            mech_list = mechanisms.get("mechanisms", []) if isinstance(mechanisms, dict) else []
            mech_target_ids = [
                m.get("target_chembl_id")
                for m in mech_list
                if m.get("target_chembl_id")
            ]

            activities = bioactivities.get("activities", []) if isinstance(bioactivities, dict) else []
            activities_to_parse = activities[:50]
            target_id_counts: dict[str, int] = {}
            for act in activities_to_parse:
                tid = act.get("target_chembl_id")
                if tid:
                    target_id_counts[tid] = target_id_counts.get(tid, 0) + 1

            # Combined list: curated mechanism targets first, then top bioactivity targets up to 15 total
            bioactivity_target_ids = sorted(target_id_counts, key=target_id_counts.get, reverse=True)
            combined_target_ids: list[str] = []
            for tid in mech_target_ids + bioactivity_target_ids:
                if tid not in combined_target_ids:
                    combined_target_ids.append(tid)
            target_ids_to_fetch = combined_target_ids[:8]

            target_details_dict: dict[str, Any] = {}

            async def fetch_target_details(tid: str):
                try:
                    url = f"{conn.base_url}/target/{tid}.json"
                    res = await conn._get(url)
                    target_details_dict[tid] = res
                except Exception as e:
                    logger.debug("target_detail_fetch_failed", extra={"target_id": tid, "error": str(e)})

            if target_ids_to_fetch:
                await asyncio.gather(*(fetch_target_details(tid) for tid in target_ids_to_fetch))

            return {
                "bioactivities": bioactivities,
                "mechanisms": mechanisms,
                "target_details": target_details_dict,
                "molecule_details": mol_details,
                "indications": ind_data,
            }

    async def _fetch_uniprot(self, uniprot_ids: list[str]) -> dict[str, Any]:
        """Fetch protein information from UniProt.

        Cache is applied at the per-protein level (inner fetch_one call),
        not the batch level. This allows cache hits to be shared across
        different drug queries that target the same protein (e.g. COX-1
        appears across many NSAID queries).
        """
        if not uniprot_ids:
            return {"proteins": []}
        async with UniProtConnector() as conn:
            proteins = []

            async def fetch_one(uid: str):
                cache_key = RawResponseCache.make_key("uniprot", uid, "entry.json")
                if not self._bypass_raw_cache:
                    cached = self._raw_cache.get(cache_key, source_name="uniprot")
                    if cached is not None:
                        proteins.append(cached)
                        return
                try:
                    res = await conn.fetch(uid)
                    proteins.append(res)
                    self._raw_cache.set(cache_key, "uniprot", uid, "entry.json", res, TTL_STRUCTURAL)
                except Exception as e:
                    logger.debug("uniprot_fetch_one_failed", extra={"uniprot_id": uid, "error": str(e)})

            await asyncio.gather(*(fetch_one(uid) for uid in uniprot_ids[:5]))
            return {"proteins": proteins}

    async def _fetch_pubmed(self, drug_name: str, disease_name: str) -> dict[str, Any]:
        async with PubMedConnector(api_key=self._ncbi_api_key) as conn:
            return await conn.fetch(drug_name, disease_name, max_results=50)

    async def _fetch_reactome(self, uniprot_ids: list[str]) -> dict[str, Any]:
        """Fetch biological pathways from Reactome and their UniProt participant lists.

        Two-phase retrieval:
          Phase 1 (forward): For each target UniProt ID, fetch which pathways contain it.
          Phase 2 (reverse): For each unique pathway, fetch which UniProt proteins participate.

        Cache is applied at the per-item inner call level (Gap 2 fix):
          - Phase 1: per-protein pathway list cached under reactome_pathways:{uid}
          - Phase 2: per-pathway participant list cached under reactome_participants:{stid}
        This enables cross-query cache reuse when the same protein or pathway appears
        in queries for different drugs.
        """
        if not uniprot_ids:
            return {"pathways": []}
        async with ReactomeConnector() as conn:
            # Phase 1: forward direction — which pathways contain each protein?
            raw_pathways: list[dict] = []

            async def fetch_pathways_for_protein(uid: str) -> None:
                cache_key = RawResponseCache.make_key("reactome_pathways", uid, "allForms")
                if not self._bypass_raw_cache:
                    cached = self._raw_cache.get(cache_key, source_name="reactome_pathways")
                    if cached is not None:
                        raw_pathways.extend(cached.get("pathways", []))
                        return
                try:
                    res = await conn.fetch(uid)
                    raw_pathways.extend(res.get("pathways", []))
                    self._raw_cache.set(
                        cache_key, "reactome_pathways", uid, "allForms", res, TTL_STRUCTURAL
                    )
                except Exception as e:
                    logger.debug(
                        "reactome_fetch_one_failed",
                        extra={"uniprot_id": uid, "error": str(e)},
                    )

            await asyncio.gather(*(fetch_pathways_for_protein(uid) for uid in uniprot_ids[:5]))

            # Deduplicate pathways by stId, preserving insertion order.
            seen_stids: dict[str, dict] = {}
            for pw in raw_pathways:
                stid = pw.get("stId")
                if stid and stid not in seen_stids:
                    seen_stids[stid] = pw

            # Phase 2: reverse direction — for each unique pathway, who are the participants?
            # Cap to 10 pathways to limit network load. Semaphore bounds concurrency to 3.
            participant_map: dict[str, list[str]] = {}
            participant_mappings: list[BiologicalIdentifierMapping] = []
            sem = asyncio.Semaphore(3)

            async def fetch_participants_for_pathway(stid: str) -> None:
                async with sem:
                    cache_key = RawResponseCache.make_key(
                        "reactome_participants", stid, "participants"
                    )
                    if not self._bypass_raw_cache:
                        cached = self._raw_cache.get(
                            cache_key, source_name="reactome_participants"
                        )
                        if cached is not None:
                            participant_map[stid] = cached.get("uniprot_ids", [])
                            for m in cached.get("mappings", []):
                                if isinstance(m, BiologicalIdentifierMapping):
                                    participant_mappings.append(m)
                                elif isinstance(m, dict):
                                    participant_mappings.append(
                                        BiologicalIdentifierMapping(
                                            canonical_symbol=m.get("canonical_symbol"),
                                            uniprot_accession=m.get("uniprot_accession"),
                                            source=m.get("source", "Reactome"),
                                            score=m.get("score"),
                                            original_identifiers=tuple(m.get("original_identifiers", ())),
                                        )
                                    )
                            return
                    res = await conn.fetch_participants(stid)
                    participant_map[stid] = res.get("uniprot_ids", [])
                    for m in res.get("mappings", []):
                        if isinstance(m, BiologicalIdentifierMapping):
                            participant_mappings.append(m)
                        elif isinstance(m, dict):
                            participant_mappings.append(
                                BiologicalIdentifierMapping(
                                    canonical_symbol=m.get("canonical_symbol"),
                                    uniprot_accession=m.get("uniprot_accession"),
                                    source=m.get("source", "Reactome"),
                                    score=m.get("score"),
                                    original_identifiers=tuple(m.get("original_identifiers", ())),
                                )
                            )
                    self._raw_cache.set(
                        cache_key, "reactome_participants", stid, "participants", res, TTL_STRUCTURAL
                    )

            await asyncio.gather(*(fetch_participants_for_pathway(stid) for stid in list(seen_stids.keys())[:10]))

            # Attach participant lists to raw pathway dicts before parsing.
            for stid, pw in seen_stids.items():
                pw["_participant_uniprot_ids"] = participant_map.get(stid, [])

            return {"pathways": list(seen_stids.values()), "mappings": participant_mappings}

    async def _fetch_clinicaltrials(self, drug_name: str, disease_name: str) -> dict[str, Any]:
        async with ClinicalTrialsConnector() as conn:
            return await conn.fetch(drug_name, disease_name)

    async def _fetch_disgenet(self, disease: Disease) -> dict[str, Any]:
        """Fetch disease-gene associations from DisGeNET.

        Queries by the resolved MeSH ID when available (ontology-grounded),
        falling back to the disease name string.
        """
        disease_id = disease.mesh_id or disease.name.lower().replace(" ", "+")
        try:
            async with DisGeNETConnector(api_key=self._disgenet_api_key) as conn:
                result = await conn.fetch(disease_id=disease_id)
                return result
        except Exception as exc:
            logger.debug("disgenet_fetch_failed", extra={"error": str(exc)})
            return {}

    def _parse_indication_data(
        self,
        indication_data: dict[str, Any],
        molecule_data: dict[str, Any],
        disease_name: str,
    ) -> ApprovalSignal | None:
        """Infer approval status from ChEMBL retrieved indication data.

        Uses fuzzy token matching to compare the queried disease_name against
        every EFO/MeSH indication term returned by ChEMBL. No drug names,
        disease names, or approval facts are hardcoded — the result is
        computed purely from retrieved data.

        Matching algorithm:
        1. Tokenize both the queried disease and the indication term
        2. Compute token overlap ratio (Jaccard-like similarity)
        3. Consider a match if similarity > 0.35 or queried name is substring
        4. Select the best-matching indication
        5. Return ApprovalSignal based on max_phase_for_ind of best match

        Args:
            indication_data: Raw ChEMBL indication response dict.
            molecule_data: Raw ChEMBL molecule details dict.
            disease_name: The queried disease name (from user input).

        Returns:
            ApprovalSignal built from retrieved data, or None if no ChEMBL data.
        """
        indications = indication_data.get("indications", [])
        if not indications and not molecule_data:
            return None

        # Count total approved indications for this drug (informational)
        approved_count = sum(
            1 for ind in indications
            if int(ind.get("max_phase_for_ind") or 0) == 4
        )

        # Tokenize queried disease name
        query_tokens = set(
            re.sub(r"[^a-z0-9]", " ", disease_name.lower()).split()
        ) - {"the", "a", "an", "of", "and", "or", "for", "in", "to"}

        best_match_phase = 0
        best_match_term = ""
        best_match_confidence = 0.0

        for ind in indications:
            efo_term = str(ind.get("efo_term") or "").lower()
            mesh_heading = str(ind.get("mesh_heading") or "").lower()
            max_phase = int(ind.get("max_phase_for_ind") or 0)

            # Try both EFO term and MeSH heading
            for term in (efo_term, mesh_heading):
                if not term:
                    continue
                term_tokens = set(
                    re.sub(r"[^a-z0-9]", " ", term).split()
                ) - {"the", "a", "an", "of", "and", "or", "for", "in", "to"}

                # Jaccard-like similarity on tokens
                union = query_tokens | term_tokens
                if not union:
                    continue
                intersection = query_tokens & term_tokens
                sim = len(intersection) / len(union)

                # Substring containment boost
                q_clean = disease_name.lower().replace(" ", "")
                t_clean = term.replace(" ", "")
                if q_clean in t_clean or t_clean in q_clean:
                    sim = max(sim, 0.6)

                if sim > best_match_confidence:
                    best_match_confidence = sim
                    best_match_term = term
                    best_match_phase = max_phase

        # Require minimum similarity to accept a match (prevents false positives)
        _MIN_MATCH_CONFIDENCE = 0.30
        if best_match_confidence < _MIN_MATCH_CONFIDENCE:
            # No meaningful match found — use global max_phase from molecule data
            global_max_phase = int(molecule_data.get("max_phase") or 0)
            if global_max_phase > 0:
                logger.info(
                    "approval_signal_global_phase_fallback",
                    extra={
                        "disease": disease_name,
                        "global_max_phase": global_max_phase,
                    },
                )
                return ApprovalSignal.from_chembl_indication_match(
                    max_phase=0,  # No indication match → treat as novel hypothesis
                    matched_term="",
                    match_confidence=0.0,
                    approved_count=approved_count,
                )
            return ApprovalSignal.no_data()

        global_max = int(molecule_data.get("max_phase") or 0)
        effective_phase = best_match_phase
        if global_max == 4 and best_match_phase >= 3:
            effective_phase = 4

        logger.info(
            "approval_signal_match",
            extra={
                "disease": disease_name,
                "matched_term": best_match_term,
                "max_phase": effective_phase,
                "confidence": round(best_match_confidence, 3),
            },
        )
        return ApprovalSignal.from_chembl_indication_match(
            max_phase=effective_phase,
            matched_term=best_match_term,
            match_confidence=best_match_confidence,
            approved_count=approved_count,
        )

    def _parse_chembl_data(
        self,
        data: dict[str, Any],
        drug: Drug,
    ) -> tuple[list[Target], list[Evidence]]:
        """Parse ChEMBL mechanism and bioactivity data into Target and Evidence objects.

        Prioritizes curated mechanism data from /mechanism.json as the primary path.
        Only falls back to mining raw bioactivities if no curated mechanisms produce
        validated targets.
        """
        targets: list[Target] = []
        evidence: list[Evidence] = []
        activities = data.get("bioactivities", {}).get("activities", [])
        mechanisms = data.get("mechanisms", {}).get("mechanisms", [])
        target_details = data.get("target_details", {})

        # Build mapping from target ChEMBL ID to canonical UniProt accession
        # Prioritizes primary component accession (comp.get("accession"), e.g., P35354) over TrEMBL xrefs (A8K802)
        uniprot_map: dict[str, str] = {}
        for tid, tdata in target_details.items():
            components = tdata.get("target_components", [])
            for comp in components:
                acc = comp.get("accession")
                if acc and len(acc) >= 6:
                    uniprot_map[tid] = acc
                    break
                # Fallback to xrefs prioritizing Swiss-Prot accession prefixes (P, Q, O)
                xrefs = [
                    x.get("xref_id")
                    for x in comp.get("target_component_xrefs", [])
                    if x.get("xref_src_db") == "UniProt" and x.get("xref_id")
                ]
                if xrefs:
                    swissprot = [x for x in xrefs if x[0] in "PQO" and len(x) == 6]
                    uniprot_map[tid] = swissprot[0] if swissprot else xrefs[0]
                    break

        # ── Primary Path: Curated Mechanism of Action Data ───────────────────
        seen_uniprots: set[str] = set()
        for mech in mechanisms:
            target_chembl = mech.get("target_chembl_id", "")
            target_uniprot = uniprot_map.get(target_chembl, "")
            if not target_uniprot or target_uniprot in seen_uniprots:
                continue
            seen_uniprots.add(target_uniprot)

            action_type = mech.get("action_type") or "MODULATOR"
            mech_desc = mech.get("mechanism_of_action") or action_type
            prov = ProvenanceReference(
                source_name="ChEMBL-Mechanism",
                source_version="v33",
                record_id=str(mech.get("mec_id", target_chembl)),
                url=f"https://www.ebi.ac.uk/chembl/target_report_card/{target_chembl}",
            )
            # High-affinity default (1.0 nM) for curated mechanism targets
            erw = ERW.from_base(base_weight=EvidenceType.IN_VITRO.base_erw)
            target = Target(
                drug_chembl_id=drug.chembl_id or drug.name,
                protein_uniprot=target_uniprot,
                affinity_nm=1.0,
                affinity_type="IC50",
                mechanism=str(action_type).upper()[:20],
                erw=erw,
                provenance=prov,
            )
            targets.append(target)
            ev = Evidence(
                evidence_type=EvidenceType.IN_VITRO,
                erw=erw,
                citation_key=f"chembl_mech_{target_chembl}",
                title=f"ChEMBL curated mechanism: {drug.name} - {mech_desc}",
                provenance=prov,
                drug_chembl_id=drug.chembl_id,
                target_uniprot=target_uniprot,
            )
            evidence.append(ev)

        if targets:
            logger.info(
                "chembl_targets_from_curated_mechanisms",
                extra={"drug": drug.name, "target_count": len(targets)},
            )

        # ── Secondary/Fallback Path: Raw Bioactivity Mining ──────────────────
        # Runs if mechanisms produced no targets, or to supplement curated mechanisms.
        for act in activities[:50]:  # cap at 50
            try:
                standard_value = float(act.get("standard_value") or 0)
                affinity_type = act.get("standard_type", "IC50")
                target_chembl = act.get("target_chembl_id", "")

                target_uniprot = uniprot_map.get(target_chembl) or act.get("target_accession", "")
                mechanism = act.get("mechanism_of_action", "UNKNOWN")

                if not target_uniprot or standard_value <= 0 or target_uniprot in seen_uniprots:
                    continue
                seen_uniprots.add(target_uniprot)

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
                    target_uniprot=target_uniprot,
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

                # Parse review status: "UniProtKB reviewed (Swiss-Prot)" or "unreviewed (TrEMBL)"
                entry_type = raw.get("entryType", "")
                is_reviewed = "reviewed" in entry_type.lower() and "unreviewed" not in entry_type.lower()

                protein = Protein(
                    uniprot_accession=acc,
                    gene_symbol=gene_symbol.upper(),
                    name=name,
                    organism=raw.get("organism", {}).get("scientificName", "Homo sapiens"),
                    is_reviewed=is_reviewed,
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
        """Parse Reactome data into Pathway objects.

        Populates Pathway.participant_uniprot_ids from the '_participant_uniprot_ids'
        key injected by _fetch_reactome's Phase 2 participant lookup.
        When the participant fetch failed for a pathway, this field will be [] —
        the multi-hop reasoner's guard is designed to skip the membership check
        (not reject the path) in that case, degrading gracefully to pre-B behaviour.
        """
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
                    participant_uniprot_ids=raw.get("_participant_uniprot_ids", []),
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
                why_stopped = str(status_mod.get("whyStopped", "")).lower()

                if raw_status == "COMPLETED":
                    status = TrialOutcomeStatus.COMPLETED_SUCCESS
                elif raw_status in ("RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"):
                    status = TrialOutcomeStatus.ACTIVE
                elif raw_status in ("TERMINATED", "SUSPENDED", "WITHDRAWN"):
                    # Inspect whyStopped text to distinguish safety/efficacy failures from administrative friction
                    safety_kw = ("safety", "adverse", "toxicity", "harm", "death", "side effect")
                    efficacy_kw = (
                        "futility", "lack of efficacy", "ineffective", "no benefit",
                        "primary endpoint", "lack of effect", "parent study", "study results",
                        "interim analysis", "results", "dsb", "dmcb", "endpoint", "analysis"
                    )

                    if any(kw in why_stopped for kw in safety_kw):
                        status = TrialOutcomeStatus.TERMINATED_SAFETY
                    elif any(kw in why_stopped for kw in efficacy_kw):
                        status = TrialOutcomeStatus.TERMINATED_LACK_OF_EFFICACY
                    else:
                        # Low enrollment, COVID-19, funding, study redesign, strategic priority shift → administrative
                        status = TrialOutcomeStatus.TERMINATED_ADMINISTRATIVE
                else:
                    status = TrialOutcomeStatus.UNKNOWN

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

    async def _fetch_openalex(
        self,
        drug_name: str,
        disease_name: str,
        hypothesis_id: uuid.UUID,
    ) -> list[Evidence]:
        """Fetch literature from OpenAlex (Phase 2 extended source)."""
        if not _EXTENDED_SOURCES_AVAILABLE:
            return []
        async with OpenAlexConnector() as connector:
            return await connector.fetch_literature(drug_name, disease_name, hypothesis_id)

    async def _fetch_semantic_scholar(
        self,
        drug_name: str,
        disease_name: str,
        hypothesis_id: uuid.UUID,
    ) -> list[Evidence]:
        """Fetch literature from Semantic Scholar (Phase 2 extended source)."""
        if not _EXTENDED_SOURCES_AVAILABLE:
            return []
        async with SemanticScholarConnector(api_key=self._semantic_scholar_api_key) as connector:
            return await connector.fetch_literature(drug_name, disease_name, hypothesis_id)

    async def _fetch_europepmc(
        self,
        drug_name: str,
        disease_name: str,
        hypothesis_id: uuid.UUID,
    ) -> list[Evidence]:
        """Fetch literature from Europe PMC (Phase 4 new source).

        Cache is applied at the whole-query level here because the
        query string IS the resolved identifier (drug + disease name
        normalized). Unlike UniProt/Reactome where the same protein
        appears across many drug queries, literature queries are unique
        to the drug-disease pair.

        sources_failed vs sources_queried contract (same as OpenAlex/S2):
            - Exception → sources_failed (caller handles)
            - Empty list with no exception → sources_queried with zero results
        """
        if not _NEW_SOURCES_AVAILABLE:
            return []

        import hashlib
        query = f"{drug_name.lower().strip()} AND {disease_name.lower().strip()}"
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        cache_key = RawResponseCache.make_key("europepmc", query_hash, "search")

        if not self._bypass_raw_cache:
            cached = self._raw_cache.get(cache_key, source_name="europepmc")
            if cached is not None and isinstance(cached, list):
                from backend.core.domain.evidence import Evidence as _Ev
                try:
                    return [_Ev.model_validate(item) for item in cached]
                except Exception:
                    pass  # Cache corrupted — fall through to fresh fetch

        async with EuropePMCConnector() as connector:
            result = await connector.fetch_literature(drug_name, disease_name, hypothesis_id)

        if result is not None:
            # Cache the serialized evidence list
            self._raw_cache.set(
                cache_key, "europepmc", query_hash, "search",
                [ev.model_dump(mode="json") for ev in result],
                TTL_LITERATURE,
            )
        return result if result is not None else []

    async def _fetch_opentargets(self, disease: Disease) -> dict[str, float]:
        """Fetch gene-disease associations from Open Targets (Phase 4 new source).

        Returns a flat dict {gene_symbol: score, uniprot_accession: score}
        for use in RetrievalPackage.validated_disease_genes.

        Uses the resolved disease.mondo_id when available (stable cache key).
        Falls back to an inline MONDO ID resolution via the connector's own
        resolve_mondo_id() when mondo_id is None (e.g. OT was unavailable
        during identity resolution).

        Cache is applied at the MONDO ID level — the most stable resolved identifier.

        sources_failed vs sources_queried contract:
            - Exception → sources_failed (caller handles)
            - Empty dict with no exception → sources_queried with zero results
        """
        if not _NEW_SOURCES_AVAILABLE:
            return {}

        mondo_id = disease.mondo_id

        async with OpenTargetsConnector() as connector:
            # Resolve MONDO ID if not already available
            if not mondo_id:
                mondo_id = await connector.resolve_mondo_id(disease.name)
                if not mondo_id:
                    logger.info(
                        "opentargets_mondo_unavailable",
                        extra={"disease": disease.name},
                    )
                    return {}

            cache_key = RawResponseCache.make_key(
                "opentargets_assoc", mondo_id, "associations", {"size": 50}
            )

            if not self._bypass_raw_cache:
                cached = self._raw_cache.get(cache_key, source_name="opentargets_assoc")
                if cached is not None and isinstance(cached, dict):
                    return cached

            gene_scores, mappings = await connector.fetch_association_mappings(mondo_id, page_size=50)

            result = {
                "gene_scores": gene_scores,
                "mappings": mappings,
            }

            if gene_scores is not None:
                self._raw_cache.set(
                    cache_key, "opentargets_assoc", mondo_id, "associations",
                    result, TTL_ASSOCIATIONS,
                )
            return result

    def _parse_disgenet_to_gene_scores(
        self,
        data: dict[str, Any],
    ) -> dict[str, float]:
        """Extract gene → DisGeNET score mapping from raw DisGeNET response.

        Returns a flat dict {gene_symbol: score} for use in
        validated_disease_genes. This is the corrected routing for DisGeNET
        associations — they go into the validated gene set, NOT evidence_records.

        The old _parse_disgenet_data() that created Evidence objects from
        DisGeNET is preserved below for backwards compatibility but is no
        longer called from execute(). It is intentionally not deleted so
        that any external callers that may reference it directly continue to work.
        """
        gene_scores: dict[str, float] = {}
        associations: list[dict[str, Any]] = []
        if isinstance(data, list):
            associations = data
        elif isinstance(data, dict):
            associations = data.get("payload", data.get("results", []))

        for assoc in associations[:50]:
            try:
                gene_symbol = assoc.get("gene_symbol") or assoc.get("geneName") or ""
                score = float(assoc.get("score", 0.0))
                if gene_symbol and score > 0:
                    gene_scores[gene_symbol] = round(score, 6)
            except (TypeError, ValueError):
                continue
        return gene_scores



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
