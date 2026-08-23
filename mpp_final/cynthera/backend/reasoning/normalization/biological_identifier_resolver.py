"""BiologicalIdentifierResolver — dynamic canonical resolution of gene/protein identifiers.

Resolves retrieved biological identifiers (gene symbols, UniProt accessions)
into canonical identities using authoritative mappings from retrieved Protein
and Gene records without static dictionaries or hardcoded lists.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, Any

from backend.core.domain.gene import Gene
from backend.core.domain.protein import Protein
from backend.core.value_objects.biological_identifier import (
    BiologicalIdentifierMapping,
    BiologicalIdentifierType,
    CanonicalBiologicalIdentifier,
)

logger = logging.getLogger(__name__)

# Official UniProtKB accession regular expression
_UNIPROT_PATTERN = re.compile(
    r"^([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9]|[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9][A-Z][A-Z0-9]{2}[0-9])(?:-[0-9]+)?$"
)
_HGNC_SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{0,15}$")


class BiologicalIdentifierResolver:
    """Resolves retrieved biological identifiers into canonical identities.

    Builds dynamic mappings from retrieved Protein, Gene, and source-provided
    BiologicalIdentifierMapping entities without static or hardcoded lookups.
    """

    def __init__(
        self,
        proteins: Iterable[Protein] = (),
        genes: Iterable[Gene] = (),
        mappings: Iterable[BiologicalIdentifierMapping | dict[str, Any]] = (),
    ) -> None:
        self._uniprot_to_symbol: dict[str, str] = {}
        self._symbol_to_uniprot: dict[str, str] = {}

        # Authoritative mappings from retrieved Protein records
        for protein in proteins:
            accession = self._clean_uniprot(getattr(protein, "uniprot_accession", None))
            symbol = getattr(protein, "gene_symbol", "") or ""
            symbol = symbol.strip().upper()
            if accession and symbol:
                self._uniprot_to_symbol[accession] = symbol
                self._symbol_to_uniprot[symbol] = accession

        # Dynamic mappings from retrieved Gene records
        for gene in genes:
            symbol = (
                getattr(gene, "hgnc_symbol", None)
                or getattr(gene, "symbol", None)
                or getattr(gene, "gene_symbol", None)
                or ""
            ).strip().upper()
            protein_ids = getattr(gene, "protein_ids", None) or []
            for accession in protein_ids:
                clean_acc = self._clean_uniprot(accession)
                if clean_acc and symbol:
                    self._uniprot_to_symbol[clean_acc] = symbol
                    self._symbol_to_uniprot[symbol] = clean_acc

        # Source-provided mappings (Open Targets, Reactome, etc.)
        for mapping in mappings:
            symbol = getattr(mapping, "canonical_symbol", None)
            if symbol is None and isinstance(mapping, dict):
                symbol = mapping.get("canonical_symbol")
            accession = getattr(mapping, "uniprot_accession", None)
            if accession is None and isinstance(mapping, dict):
                accession = mapping.get("uniprot_accession")

            clean_acc = self._clean_uniprot(accession)
            clean_sym = symbol.strip().upper() if symbol else ""

            if clean_acc and clean_sym:
                self._uniprot_to_symbol[clean_acc] = clean_sym
                self._symbol_to_uniprot[clean_sym] = clean_acc

    @staticmethod
    def _clean_uniprot(identifier: str | None) -> str:
        """Strip isoform suffix and whitespace from UniProt accession."""
        if not identifier:
            return ""
        return str(identifier).split("-")[0].strip().upper()

    @classmethod
    def _classify_identifier(cls, raw: str) -> BiologicalIdentifierType:
        """Classify biological identifier type based on structural patterns."""
        norm = raw.strip().upper()
        if not norm:
            return BiologicalIdentifierType.UNKNOWN
        if bool(_UNIPROT_PATTERN.match(norm)):
            return BiologicalIdentifierType.UNIPROT
        if bool(_HGNC_SYMBOL_PATTERN.match(norm)):
            return BiologicalIdentifierType.GENE_SYMBOL
        return BiologicalIdentifierType.UNKNOWN

    def resolve(
        self,
        identifier: str,
        source: str,
        confidence: float | None = None,
    ) -> CanonicalBiologicalIdentifier:
        """Resolve a biological identifier to its canonical representation.

        Args:
            identifier: Raw biological identifier string.
            source: Name of the originating source/connector.
            confidence: Optional confidence or association score.

        Returns:
            CanonicalBiologicalIdentifier with canonical key, symbol (if resolvable),
            classification, and preserved provenance.
        """
        raw = str(identifier).strip() if identifier is not None else ""
        if not raw:
            return CanonicalBiologicalIdentifier(
                canonical_identifier="",
                canonical_symbol=None,
                identifier_type=BiologicalIdentifierType.UNKNOWN,
                original_identifier=str(identifier) if identifier is not None else "",
                source=source,
                confidence=confidence,
                source_identifiers=(),
            )

        norm = raw.upper()
        clean = self._clean_uniprot(norm)

        # 1. Direct lookup in dynamic mappings: known UniProt accession
        if clean in self._uniprot_to_symbol:
            symbol = self._uniprot_to_symbol[clean]
            return CanonicalBiologicalIdentifier(
                canonical_identifier=clean,
                canonical_symbol=symbol,
                identifier_type=BiologicalIdentifierType.UNIPROT,
                original_identifier=raw,
                source=source,
                confidence=confidence,
                source_identifiers=(raw, symbol),
            )

        # 2. Direct lookup in dynamic mappings: known Gene Symbol
        if norm in self._symbol_to_uniprot:
            accession = self._symbol_to_uniprot[norm]
            return CanonicalBiologicalIdentifier(
                canonical_identifier=accession,
                canonical_symbol=norm,
                identifier_type=BiologicalIdentifierType.GENE_SYMBOL,
                original_identifier=raw,
                source=source,
                confidence=confidence,
                source_identifiers=(raw, accession),
            )

        # 3. Structural classification fallback for unmapped identifiers
        id_type = self._classify_identifier(raw)

        if id_type == BiologicalIdentifierType.UNIPROT:
            return CanonicalBiologicalIdentifier(
                canonical_identifier=clean,
                canonical_symbol=None,
                identifier_type=BiologicalIdentifierType.UNIPROT,
                original_identifier=raw,
                source=source,
                confidence=confidence,
                source_identifiers=(raw,),
            )

        if id_type == BiologicalIdentifierType.GENE_SYMBOL:
            return CanonicalBiologicalIdentifier(
                canonical_identifier=norm,
                canonical_symbol=norm,
                identifier_type=BiologicalIdentifierType.GENE_SYMBOL,
                original_identifier=raw,
                source=source,
                confidence=confidence,
                source_identifiers=(raw,),
            )

        return CanonicalBiologicalIdentifier(
            canonical_identifier=norm,
            canonical_symbol=None,
            identifier_type=BiologicalIdentifierType.UNKNOWN,
            original_identifier=raw,
            source=source,
            confidence=confidence,
            source_identifiers=(raw,),
        )
