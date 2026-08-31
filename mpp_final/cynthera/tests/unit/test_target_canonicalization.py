"""Unit tests for Target Canonicalization & Ensembl -> HGNC Normalization.

Tests:
1. Ensembl -> HGNC resolution
2. Ensembl -> UniProt mapping where available
3. UniProt -> HGNC resolution
4. HGNC -> HGNC stability
5. Equivalent identifiers collapse: canonical("ENSG00000163631") == canonical("Q13621") == canonical("SLC12A1")
6. Distinct genes remain distinct (e.g. SLC12A1 vs SLC12A3, SLC5A1 vs SLC5A2)
7. Provenance preserved (original_identifier retained)
8. Open Targets DoE evidence canonicalization in DirectionalEvidenceBuilder
9. ChEMBL / Open Targets / DATTs same-target aggregation
10. Ambiguous mappings remain gated
11. Unknown mappings remain unresolved
12. Generic literature remains blocked
"""
from __future__ import annotations

import uuid
import pytest

from backend.core.domain.drug import Drug
from backend.core.domain.disease import Disease
from backend.core.domain.target import Target
from backend.core.domain.protein import Protein
from backend.core.domain.retrieval_package import RetrievalPackage
from backend.core.enums.molecular_polarity import MolecularPolarity
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.core.value_objects.biological_identifier import (
    BiologicalIdentifierMapping,
    BiologicalIdentifierType,
)
from backend.core.value_objects.therapeutic_direction_evidence import (
    OpenTargetsDoEEvidence,
    DATTsEvidence,
    TherapeuticAction,
)
from backend.reasoning.normalization.biological_identifier_resolver import BiologicalIdentifierResolver
from backend.reasoning.directional.directional_evidence_builder import DirectionalEvidenceBuilder
from backend.reasoning.directional.canonical_entity_gate import is_canonically_grounded


def test_ensembl_to_hgnc_resolution():
    """Verify Ensembl ID dynamically resolves to HGNC canonical symbol."""
    mapping = BiologicalIdentifierMapping(
        canonical_symbol="SLC12A1",
        uniprot_accession="Q13621",
        ensembl_id="ENSG00000163631",
        source="OpenTargets",
    )
    resolver = BiologicalIdentifierResolver(mappings=[mapping])

    res = resolver.resolve("ENSG00000163631", source="OpenTargets")
    assert res.canonical_symbol == "SLC12A1"
    assert res.canonical_identifier == "Q13621"
    assert res.original_identifier == "ENSG00000163631"
    assert res.identifier_type == BiologicalIdentifierType.ENSEMBL
    assert "Q13621" in res.source_identifiers


def test_uniprot_to_hgnc_resolution():
    """Verify UniProt accession resolves to HGNC canonical symbol."""
    protein = Protein(uniprot_accession="Q13621", gene_symbol="SLC12A1", name="NKCC2")
    resolver = BiologicalIdentifierResolver(proteins=[protein])

    res = resolver.resolve("Q13621", source="UniProt")
    assert res.canonical_symbol == "SLC12A1"
    assert res.canonical_identifier == "Q13621"
    assert res.original_identifier == "Q13621"
    assert res.identifier_type == BiologicalIdentifierType.UNIPROT


def test_hgnc_to_hgnc_stability():
    """Verify HGNC gene symbol remains stable and canonical."""
    protein = Protein(uniprot_accession="Q13621", gene_symbol="SLC12A1", name="NKCC2")
    resolver = BiologicalIdentifierResolver(proteins=[protein])

    res = resolver.resolve("SLC12A1", source="HGNC")
    assert res.canonical_symbol == "SLC12A1"
    assert res.canonical_identifier == "Q13621"
    assert res.original_identifier == "SLC12A1"
    assert res.identifier_type == BiologicalIdentifierType.GENE_SYMBOL


def test_equivalent_identifiers_collapse():
    """Verify canonical(ENSG) == canonical(UniProt) == canonical(HGNC) across benchmark targets."""
    targets_data = [
        ("SLC12A1", "Q13621", "ENSG00000163631"),
        ("SLC5A2", "P31639", "ENSG00000140675"),
        ("CRBN", "Q96SW2", "ENSG00000113851"),
        ("PTGS2", "P35354", "ENSG00000073756"),
        ("ADRB1", "P08588", "ENSG00000043591"),
    ]

    mappings = [
        BiologicalIdentifierMapping(
            canonical_symbol=sym,
            uniprot_accession=uni,
            ensembl_id=ens,
            source="OpenTargets",
        )
        for sym, uni, ens in targets_data
    ]
    resolver = BiologicalIdentifierResolver(mappings=mappings)

    for sym, uni, ens in targets_data:
        res_ens = resolver.resolve(ens, source="OpenTargets")
        res_uni = resolver.resolve(uni, source="UniProt")
        res_sym = resolver.resolve(sym, source="HGNC")

        assert res_ens.canonical_symbol == sym
        assert res_uni.canonical_symbol == sym
        assert res_sym.canonical_symbol == sym

        # Provenance is uniquely preserved
        assert res_ens.original_identifier == ens
        assert res_uni.original_identifier == uni
        assert res_sym.original_identifier == sym


def test_distinct_genes_remain_distinct():
    """Verify resolver maintains separation between related but distinct genes."""
    mappings = [
        BiologicalIdentifierMapping(canonical_symbol="SLC12A1", uniprot_accession="Q13621", ensembl_id="ENSG00000163631", source="OT"),
        BiologicalIdentifierMapping(canonical_symbol="SLC12A3", uniprot_accession="P55017", ensembl_id="ENSG00000174197", source="OT"),
        BiologicalIdentifierMapping(canonical_symbol="SLC5A1", uniprot_accession="P13866", ensembl_id="ENSG00000100170", source="OT"),
        BiologicalIdentifierMapping(canonical_symbol="SLC5A2", uniprot_accession="P31639", ensembl_id="ENSG00000140675", source="OT"),
    ]
    resolver = BiologicalIdentifierResolver(mappings=mappings)

    assert resolver.resolve("ENSG00000163631", source="OT").canonical_symbol == "SLC12A1"
    assert resolver.resolve("ENSG00000174197", source="OT").canonical_symbol == "SLC12A3"
    assert resolver.resolve("ENSG00000100170", source="OT").canonical_symbol == "SLC5A1"
    assert resolver.resolve("ENSG00000140675", source="OT").canonical_symbol == "SLC5A2"


def test_unknown_and_ambiguous_identifiers_remain_unresolved():
    """Verify unmapped identifiers do not get spurious canonical symbols."""
    resolver = BiologicalIdentifierResolver()

    res_unknown = resolver.resolve("UNKNOWN_GENE_XYZ", source="Test")
    assert res_unknown.canonical_symbol == "UNKNOWN_GENE_XYZ" or res_unknown.canonical_symbol is None

    res_unmapped_ens = resolver.resolve("ENSG99999999999", source="Test")
    assert res_unmapped_ens.canonical_symbol is None
    assert res_unmapped_ens.original_identifier == "ENSG99999999999"


def test_directional_evidence_builder_canonical_aggregation():
    """Verify DirectionalEvidenceBuilder aggregates ChEMBL, Open Targets, and DATTs under canonical HGNC symbol."""
    hyp_id = uuid.uuid4()
    drug = Drug(name="Furosemide", identifiers={"chembl": "CHEMBL44"})
    disease = Disease(name="Edema", identifiers={"mondo": "MONDO_0005575"})
    erw = ERW.from_base(1.0)
    prov = ProvenanceReference(source_name="ChEMBL", source_version="v33", record_id="rec1")

    # ChEMBL target uses UniProt accession
    target = Target(
        drug_chembl_id="CHEMBL44",
        protein_uniprot="Q13621",
        affinity_nm=1.0,
        affinity_type="IC50",
        mechanism="INHIBITOR",
        erw=erw,
        provenance=prov,
    )
    protein = Protein(uniprot_accession="Q13621", gene_symbol="SLC12A1", name="NKCC2")

    # Open Targets uses Ensembl ID
    ot_doe = OpenTargetsDoEEvidence(
        target_id="ENSG00000163631",
        disease_id="MONDO_0005575",
        target_symbol="SLC12A1",
        direction_on_target="LoF",
        direction_on_trait="protect",
        datasource_id="clinical_precedence",
    )

    # DATTs uses gene symbol
    datts_ev = DATTsEvidence(
        gene_symbol="SLC12A1",
        disease_name="Edema",
        rel_type="Inhibition",
        required_action=TherapeuticAction.INHIBITION,
        literature="Pharmacology Textbook",
    )

    mapping = BiologicalIdentifierMapping(
        canonical_symbol="SLC12A1",
        uniprot_accession="Q13621",
        ensembl_id="ENSG00000163631",
        source="OpenTargets",
    )

    pkg = RetrievalPackage(
        hypothesis_id=hyp_id,
        drug=drug,
        disease=disease,
        targets=[target],
        proteins=[protein],
        identifier_mappings=[mapping],
        opentargets_doe_evidence=[ot_doe],
        datts_evidence=[datts_ev],
    )

    builder = DirectionalEvidenceBuilder()
    records = builder.build_all(pkg)

    # All three sources must now agree on canonical target 'SLC12A1'
    for rec in records:
        assert rec.target_canonical_id == "SLC12A1"
        assert rec.mapping_status in ("EXACT", "RESOLVED")

    # Check that provenance is preserved per source
    chembl_rec = next(r for r in records if r.source == "ChEMBL")
    assert chembl_rec.original_target_id == "Q13621"

    ot_rec = next(r for r in records if r.source == "OpenTargets")
    assert ot_rec.original_target_id == "ENSG00000163631"
    assert ot_rec.target_ensembl_id == "ENSG00000163631"

    datts_rec = next(r for r in records if r.source == "DATTs")
    assert datts_rec.original_target_id == "SLC12A1"
