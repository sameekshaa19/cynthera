"""Value objects package."""
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.identifier import ResolvedIdentifierSet, CanonicalIdentifier
from backend.core.value_objects.provenance import ProvenanceReference

__all__ = ["ERW", "ResolvedIdentifierSet", "CanonicalIdentifier", "ProvenanceReference"]
