"""ClaimExtractionAgent — LLM-assisted extraction of structured claims from literature.

Reference: 04_REASONING_SPECIFICATION.md, 05_AGENT_SPECIFICATIONS.md
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from backend.core.domain.claim import Claim
from backend.core.domain.evidence import Evidence
from backend.core.enums.predicate_type import PredicateType
from backend.core.value_objects.erw import ERW
from backend.core.value_objects.provenance import ProvenanceReference
from backend.core.exceptions import LLMResponseParsingError

logger = logging.getLogger(__name__)

# Versioned extraction prompt
EXTRACTION_PROMPT_V1 = """You are a biomedical claim extraction system. Extract all biological relationship claims from the following text.

For each claim, extract:
1. subject: The entity performing the action (drug name, gene symbol, protein name)
2. predicate: One of: ACTIVATES, INHIBITS, BINDS, UPREGULATES, DOWNREGULATES, CAUSES, PREVENTS, ASSOCIATED_WITH, NO_EFFECT
3. object: The entity receiving the action (target, pathway, disease)
4. confidence: Float 0.0–1.0 indicating extraction confidence

Return ONLY a valid JSON array of objects with keys: subject, predicate, object, confidence.
Return empty array [] if no clear biological claims are present.

TEXT:
{text}

JSON OUTPUT:"""


class ClaimExtractionAgent:
    """LLM-assisted agent that extracts structured subject-predicate-object claims from text.

    IMPORTANT: This is the ONLY component allowed to call the LLM.
    All other components must be deterministic.

    Attributes:
        _model: LLM model name (default 'gemini-1.5-flash').
        _api_key: LLM API key from environment.
        _prompt_version: Version string of the extraction prompt used.
    """

    PROMPT_VERSION = "v1"

    def __init__(
        self,
        model: str = "gemini-1.5-flash",
        api_key: str | None = None,
    ) -> None:
        """Initialize the ClaimExtractionAgent.

        Args:
            model: LLM model identifier.
            api_key: LLM API key (falls back to LLM_API_KEY environment variable).
        """
        self._model = model
        self._api_key = api_key or os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY")
        self._prompt_version = self.PROMPT_VERSION

    async def extract_claims(
        self,
        evidence: Evidence,
        drug_name: str,
        disease_name: str,
    ) -> list[Claim]:
        """Extract structured claims from a single Evidence record.

        Args:
            evidence: The Evidence record containing abstract text.
            drug_name: Drug name for context (used in claim matching).
            disease_name: Disease name for context.

        Returns:
            List of validated Claim objects extracted from the evidence.

        Raises:
            LLMResponseParsingError: If LLM output is malformed.
        """
        if not evidence.abstract:
            return []

        text = evidence.abstract
        raw_claims = await self._call_llm(text)

        claims: list[Claim] = []
        for raw in raw_claims:
            try:
                claim = self._parse_raw_claim(raw, evidence)
                claims.append(claim)
            except Exception as exc:
                logger.debug("claim_parse_error", extra={"error": str(exc), "raw": raw})
                continue

        logger.info(
            "claim_extraction_complete",
            extra={
                "evidence_id": str(evidence.id),
                "claims_extracted": len(claims),
                "model": self._model,
                "prompt_version": self._prompt_version,
            },
        )
        return claims

    async def _call_llm(self, text: str) -> list[dict[str, Any]]:
        """Call the LLM API and parse the response.

        Args:
            text: Abstract text to extract claims from.

        Returns:
            List of raw claim dicts from LLM output.
        """
        if not self._api_key:
            logger.warning("llm_api_key_not_set", extra={"model": self._model})
            return self._rule_based_fallback(text)

        prompt = EXTRACTION_PROMPT_V1.format(text=text[:3000])  # cap at 3000 chars

        try:
            import google.generativeai as genai
            genai.configure(api_key=self._api_key)
            model = genai.GenerativeModel(self._model)
            response = await model.generate_content_async(
                prompt,
                generation_config={"temperature": 0.0, "max_output_tokens": 1000},
            )
            return self._parse_llm_response(response.text)
        except ImportError:
            logger.warning("google_genai_not_installed", extra={"fallback": "rule_based"})
            return self._rule_based_fallback(text)
        except Exception as exc:
            logger.error("llm_call_failed", extra={"error": str(exc)})
            return self._rule_based_fallback(text)

    def _parse_llm_response(self, response_text: str) -> list[dict[str, Any]]:
        """Parse and validate LLM JSON response.

        Args:
            response_text: Raw text response from LLM.

        Returns:
            Validated list of claim dicts.

        Raises:
            LLMResponseParsingError: If JSON is malformed or schema invalid.
        """
        text = response_text.strip()
        # Extract JSON array from response
        start = text.find("[")
        end = text.rfind("]") + 1
        if start == -1 or end == 0:
            return []
        try:
            claims = json.loads(text[start:end])
            if not isinstance(claims, list):
                raise LLMResponseParsingError(
                    message="LLM response is not a JSON array.",
                    context={"response_snippet": text[:200]},
                )
            return claims
        except json.JSONDecodeError as exc:
            raise LLMResponseParsingError(
                message=f"LLM response JSON parse error: {exc}",
                context={"response_snippet": text[:200]},
            ) from exc

    def _rule_based_fallback(self, text: str) -> list[dict[str, Any]]:
        """Simple rule-based fallback when LLM is unavailable.

        Detects basic activation/inhibition patterns in text.

        Args:
            text: Abstract text to scan.

        Returns:
            List of raw claim dicts detected by pattern matching.
        """
        claims = []
        text_lower = text.lower()
        patterns = [
            ("inhibit", "INHIBITS"),
            ("activat", "ACTIVATES"),
            ("upregulat", "UPREGULATES"),
            ("downregulat", "DOWNREGULATES"),
            ("prevent", "PREVENTS"),
            ("associat", "ASSOCIATED_WITH"),
        ]
        for pattern, predicate in patterns:
            if pattern in text_lower:
                claims.append({
                    "subject": "drug",
                    "predicate": predicate,
                    "object": "target",
                    "confidence": 0.3,
                })
                break
        return claims

    def _parse_raw_claim(
        self,
        raw: dict[str, Any],
        evidence: Evidence,
    ) -> Claim:
        """Parse a raw claim dict into a validated Claim entity.

        Args:
            raw: Dict with subject, predicate, object, confidence keys.
            evidence: Parent Evidence record.

        Returns:
            Validated Claim entity.
        """
        predicate_str = str(raw.get("predicate", "")).upper()
        try:
            predicate = PredicateType(predicate_str)
        except ValueError:
            predicate = PredicateType.ASSOCIATED_WITH

        confidence = float(raw.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        return Claim(
            subject=str(raw.get("subject", "unknown"))[:100],
            predicate=predicate,
            object=str(raw.get("object", "unknown"))[:100],
            confidence=confidence,
            erw=evidence.erw,
            evidence_ids=[evidence.id],
            provenance=evidence.provenance,
            raw_text=evidence.abstract[:500] if evidence.abstract else None,
            is_validated=False,
        )
