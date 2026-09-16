"""Fail-closed semantic gates for therapeutic support evidence."""
from __future__ import annotations

import re
from enum import Enum
from typing import Any


class TherapeuticDirection(str, Enum):
    TREATS = "TREATS"
    IMPROVES = "IMPROVES"
    REDUCES = "REDUCES"
    PROTECTS = "PROTECTS"
    WORSENS = "WORSENS"
    CAUSES = "CAUSES"
    INCREASES_RISK = "INCREASES_RISK"
    ASSOCIATED_WITH_HARM = "ASSOCIATED_WITH_HARM"
    ADVERSE_EVENT = "ADVERSE_EVENT"
    UNKNOWN = "UNKNOWN"


_HARMFUL_DIRECTION_PATTERNS: tuple[tuple[TherapeuticDirection, str], ...] = (
    (TherapeuticDirection.INCREASES_RISK, r"\brisk factor\b"),
    (TherapeuticDirection.INCREASES_RISK, r"\b(?:increased|higher|elevated)\s+risk\b"),
    (TherapeuticDirection.ASSOCIATED_WITH_HARM, r"\bassociated with\s+(?:an?\s+)?(?:harm|toxicity|worsening|poor|adverse)\b"),
    (TherapeuticDirection.ADVERSE_EVENT, r"\badverse\s+(?:event|effect|outcome)s?\b"),
    (TherapeuticDirection.CAUSES, r"\b(?:drug[- ]induced|causes?|etiologic(?:al)?)\b"),
    (TherapeuticDirection.WORSENS, r"\b(?:worsen(?:s|ed|ing)?|increases?\s+(?:disease|symptom)\s+severity)\b"),
    (TherapeuticDirection.WORSENS, r"\b(?:failed|failure|no)\s+(?:to\s+)?(?:improve|benefit|efficacy|response)\b"),
)
_THERAPEUTIC_DIRECTION_PATTERNS: tuple[tuple[TherapeuticDirection, str], ...] = (
    (TherapeuticDirection.IMPROVES, r"\bimprov(?:e|ed|ement|ing)s?\b"),
    (TherapeuticDirection.REDUCES, r"\breduc(?:e|ed|es|ing)\b"),
    (TherapeuticDirection.PROTECTS, r"\bprotect(?:s|ed|ion|ing)?\b"),
    (TherapeuticDirection.TREATS, r"\btreat(?:s|ed|ment|ing)?\b"),
)


def classify_therapeutic_direction(evidence: Any) -> tuple[TherapeuticDirection, str]:
    """Classify explicit direction before deciding whether evidence can support."""
    text = " ".join(
        str(value or "") for value in (
            getattr(evidence, "title", None),
            getattr(evidence, "abstract", None),
        )
    ).lower()
    if not text.strip():
        return TherapeuticDirection.UNKNOWN, "No text available."
    for direction, pattern in _HARMFUL_DIRECTION_PATTERNS:
        if re.search(pattern, text):
            return direction, "Explicit non-therapeutic harmful, adverse, risk, or failure direction detected."
    for direction, pattern in _THERAPEUTIC_DIRECTION_PATTERNS:
        if re.search(pattern, text):
            return direction, "Explicit therapeutic direction detected."
    return TherapeuticDirection.UNKNOWN, "No explicit therapeutic direction detected."


def is_therapeutically_eligible_evidence(evidence: Any) -> tuple[bool, str]:
    """Return whether a record can contribute direct therapeutic support."""
    direction, reason = classify_therapeutic_direction(evidence)
    harmful = {
        TherapeuticDirection.WORSENS,
        TherapeuticDirection.CAUSES,
        TherapeuticDirection.INCREASES_RISK,
        TherapeuticDirection.ASSOCIATED_WITH_HARM,
        TherapeuticDirection.ADVERSE_EVENT,
    }
    return direction not in harmful, reason
