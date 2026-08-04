"""ClaimExtractionAgent — LLM-assisted extraction of structured claims from literature.

Reference: 04_REASONING_SPECIFICATION.md, 05_AGENT_SPECIFICATIONS.md
"""
from __future__ import annotations

import asyncio
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
        _model: LLM model name (default 'gemini-2.0-flash').
        _api_key: LLM API key from environment.
        _prompt_version: Version string of the extraction prompt used.
        _last_extraction_method: Tracks whether the last call used LLM or rule-based fallback.
            Set per call to 'llm' or 'rule_based_fallback'. Used for audit disclosure.
    """

    PROMPT_VERSION = "v1"

    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        api_key: str | None = None,
    ) -> None:
        """Initialize the ClaimExtractionAgent.

        Args:
            model: LLM model identifier.
            api_key: LLM API key (falls back to LLM_API_KEY / GEMINI_API_KEY environment variable).
        """
        self._model = model
        self._api_key = api_key or os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY")
        self._prompt_version = self.PROMPT_VERSION
        # Tracks extraction path per call — set before every return in _call_llm.
        # 'llm' = LLM succeeded. 'rule_based_fallback' = LLM unavailable or failed.
        self._last_extraction_method: str = "llm"

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
        raw_claims = await self._call_llm(text, drug_name, disease_name)

        claims: list[Claim] = []
        for raw in raw_claims:
            try:
                claim = self._parse_raw_claim(
                    raw,
                    evidence,
                    extraction_method=self._last_extraction_method,
                )
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
                "extraction_method": self._last_extraction_method,
            },
        )
        return claims

    async def _call_llm(self, text: str, drug_name: str = "drug", disease_name: str = "disease") -> list[dict[str, Any]]:
        """Call the LLM API and parse the response.

        Args:
            text: Abstract text to extract claims from.
            drug_name: Drug name for context-aware extraction.
            disease_name: Disease name for context-aware extraction.

        Returns:
            List of raw claim dicts from LLM output.
        """
        if not self._api_key:
            logger.warning(
                "llm_api_key_not_set",
                extra={"model": self._model, "fallback": "rule_based_fallback"},
            )
            self._last_extraction_method = "rule_based_fallback"
            return self._rule_based_fallback(text, drug_name, disease_name)

        prompt = EXTRACTION_PROMPT_V1.format(text=text[:3000])  # cap at 3000 chars

        try:
            from google import genai as google_genai
            from google.genai import types as genai_types

            client = google_genai.Client(api_key=self._api_key)
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self._model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=1000,
                ),
            )
            self._last_extraction_method = "llm"
            return self._parse_llm_response(response.text)

        except ImportError:
            logger.warning(
                "google_genai_not_installed",
                extra={"fallback": "rule_based_fallback", "hint": "pip install google-genai"},
            )
            self._last_extraction_method = "rule_based_fallback"
            return self._rule_based_fallback(text, drug_name, disease_name)

        except Exception as exc:
            # Distinguish API-level failures (rate limit, bad key) from SDK-level failures.
            # Both are logged with the error class for debuggability.
            logger.error(
                "llm_call_failed",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "model": self._model,
                    "fallback": "rule_based_fallback",
                },
            )
            self._last_extraction_method = "rule_based_fallback"
            return self._rule_based_fallback(text, drug_name, disease_name)

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

    def _rule_based_fallback(self, text: str, drug_name: str = "drug", disease_name: str = "disease") -> list[dict[str, Any]]:
        """Context-aware rule-based fallback when LLM is unavailable.

        Uses drug and disease names from context to produce meaningful claims
        rather than generic placeholders.

        IMPORTANT: Claims produced by this method are low-confidence (0.25) keyword-matched
        guesses, not LLM-verified biological assertions. They must be disclosed as such in
        the audit report. The _last_extraction_method field on the agent is set to
        'rule_based_fallback' before this method is called, enabling upstream disclosure.

        Args:
            text: Abstract text to scan.
            drug_name: Drug name for subject/object labeling.
            disease_name: Disease name for object labeling.

        Returns:
            List of raw claim dicts detected by pattern matching. At most one claim per call.
        """
        claims = []
        text_lower = text.lower()
        drug_lower = drug_name.lower()
        disease_lower = disease_name.lower()

        # Determine the primary object: disease name if mentioned, else generic "target"
        primary_object = disease_name if disease_lower in text_lower else "molecular target"

        patterns = [
            ("inhibit", "INHIBITS"),
            ("activat", "ACTIVATES"),
            ("upregulat", "UPREGULATES"),
            ("downregulat", "DOWNREGULATES"),
            ("prevent", "PREVENTS"),
            ("associat", "ASSOCIATED_WITH"),
            ("bind", "BINDS"),
            ("caus", "CAUSES"),
        ]
        for pattern, predicate in patterns:
            if pattern in text_lower:
                # Use drug name as subject if found in text, else fallback to "compound"
                subject = drug_name if drug_lower in text_lower else "compound"
                claims.append({
                    "subject": subject,
                    "predicate": predicate,
                    "object": primary_object,
                    "confidence": 0.25,  # Low confidence for rule-based extraction
                })
                break
        return claims

    def _parse_raw_claim(
        self,
        raw: dict[str, Any],
        evidence: Evidence,
        extraction_method: str = "llm",
    ) -> Claim:
        """Parse a raw claim dict into a validated Claim entity.

        Args:
            raw: Dict with subject, predicate, object, confidence keys.
            evidence: Parent Evidence record.
            extraction_method: 'llm' or 'rule_based_fallback'. Disclosed in raw_text prefix.

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

        # Disclose extraction method in raw_text so audit reports can surface it.
        # Rule-based claims are prefixed to distinguish them from LLM-verified claims.
        abstract_snippet = evidence.abstract[:500] if evidence.abstract else None
        if extraction_method == "rule_based_fallback" and abstract_snippet:
            raw_text = f"[keyword-extracted — LLM unavailable] {abstract_snippet}"
        else:
            raw_text = abstract_snippet

        return Claim(
            subject=str(raw.get("subject", "unknown"))[:100],
            predicate=predicate,
            object=str(raw.get("object", "unknown"))[:100],
            confidence=confidence,
            erw=evidence.erw,
            evidence_ids=[evidence.id],
            provenance=evidence.provenance,
            raw_text=raw_text,
            is_validated=False,
        )
