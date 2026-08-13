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

from backend.infrastructure.cache.raw_response_cache import RawResponseCache, TTL_LITERATURE

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
        _model: LLM model name.
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
        db_path: str = "data/cynthera.db",
    ) -> None:
        """Initialize the ClaimExtractionAgent.

        Args:
            model: LLM model identifier.
            api_key: LLM API key (falls back to GROQ_API_KEY / LLM_API_KEY / GEMINI_API_KEY environment variable).
            db_path: Path to SQLite database file for claim caching.
        """
        self._model = model
        self._api_key = api_key or os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY")
        self._prompt_version = self.PROMPT_VERSION
        self._last_extraction_method: str = "llm"
        self._has_logged_unconfigured_warning: bool = False
        self._raw_cache = RawResponseCache(db_path=db_path) if db_path else None
        self._sem = asyncio.Semaphore(3)  # Bound concurrent LLM calls to 3 to prevent TPM/RPM bursts

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
            disease_name: Disease name for context (used in claim matching).

        Returns:
            List of Claim entities extracted from the evidence record.
        """
        if not evidence.abstract:
            logger.info("evidence_abstract_missing", extra={"evidence_id": str(evidence.id)})
            return []

        # Check raw cache for previously extracted claims
        import hashlib
        abstract_hash = hashlib.sha256(evidence.abstract.encode()).hexdigest()[:16]
        cache_key = ""
        if self._raw_cache:
            cache_key = RawResponseCache.make_key(
                "llm_claims",
                evidence.citation_key or abstract_hash,
                "extract_v1",
                {"drug": drug_name.lower().strip(), "disease": disease_name.lower().strip()},
            )
            cached = self._raw_cache.get(cache_key, source_name="llm_claims")
            if cached is not None and isinstance(cached, dict):
                method = cached.get("method", "llm")
                raw_claims = cached.get("claims", [])
                self._last_extraction_method = method
                claims: list[Claim] = []
                for raw in raw_claims:
                    try:
                        claim = self._parse_raw_claim(raw, evidence, extraction_method=method)
                        claims.append(claim)
                    except Exception:
                        continue
                return claims

        raw_claims = await self._call_llm(evidence.abstract, drug_name, disease_name)

        # Store extraction in raw cache for instant 0ms response on future calls
        if self._raw_cache and cache_key and raw_claims:
            self._raw_cache.set(
                cache_key,
                "llm_claims",
                evidence.citation_key or abstract_hash,
                "extract_v1",
                {"claims": raw_claims, "method": self._last_extraction_method},
                TTL_LITERATURE,
            )

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
        async with self._sem:
            groq_key = self._api_key if (self._api_key and self._api_key.startswith("gsk_")) else os.environ.get("GROQ_API_KEY")
            gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_API_KEY")

            # Validate keys (ignore unconfigured placeholders)
            has_valid_groq = bool(groq_key and not groq_key.startswith("gsk_your_groq"))
            has_valid_gemini = bool(gemini_key and not gemini_key.startswith("your_"))

            if has_valid_groq:
                prompt = EXTRACTION_PROMPT_V1.format(text=text[:3000])
                # Default to llama-3.1-8b-instant for fast, low-latency, high-throughput Groq extraction
                model_name = self._model if ("8b" in self._model or "instant" in self._model) else "llama-3.1-8b-instant"
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                }
                body = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "max_tokens": 1000,
                }
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        for attempt in range(4):
                            resp = await client.post(url, headers=headers, json=body)
                            if resp.status_code == 429:
                                # Groq free tier rate limit — back off and retry
                                retry_delay = float(resp.headers.get("retry-after", 1.5)) + (attempt * 0.5)
                                logger.info(
                                    "groq_rate_limit_backoff",
                                    extra={"attempt": attempt + 1, "retry_delay": retry_delay},
                                )
                                await asyncio.sleep(retry_delay)
                                continue
                            resp.raise_for_status()
                            data = resp.json()
                            response_text = data["choices"][0]["message"]["content"]
                            self._last_extraction_method = "llm"
                            return self._parse_llm_response(response_text)
                except Exception as exc:
                    logger.error(
                        f"llm_call_failed: provider=groq model={model_name} [{type(exc).__name__}] {exc}",
                        extra={
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                            "model": model_name,
                            "fallback": "rule_based_fallback",
                        },
                    )
                    self._last_extraction_method = "rule_based_fallback"
                    return self._rule_based_fallback(text, drug_name, disease_name)

            elif has_valid_gemini:
                prompt = EXTRACTION_PROMPT_V1.format(text=text[:3000])
                try:
                    from google import genai as google_genai
                    from google.genai import types as genai_types

                    client = google_genai.Client(api_key=gemini_key)
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=self._model if self._model.startswith("gemini") else "gemini-2.0-flash",
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
                    logger.error(
                        f"llm_call_failed: provider=google model={self._model} [{type(exc).__name__}] {exc}",
                        extra={
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                            "model": self._model,
                            "fallback": "rule_based_fallback",
                        },
                    )
                    self._last_extraction_method = "rule_based_fallback"
                    return self._rule_based_fallback(text, drug_name, disease_name)

            else:
                if not self._has_logged_unconfigured_warning:
                    logger.info(
                        "llm_key_unconfigured_fallback_to_rule_based",
                        extra={"fallback": "rule_based_fallback", "hint": "Set GROQ_API_KEY or GEMINI_API_KEY in .env"},
                    )
                    self._has_logged_unconfigured_warning = True
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

        erw = evidence.erw
        # Rule-based keyword matching has higher false-positive rates than LLM extraction.
        # Apply a 0.5x weight discount so unverified keyword claims carry less weight
        # and do not over-inflate Support Scores or drive heavy contradiction penalties.
        if extraction_method == "rule_based_fallback":
            erw = ERW.from_base(evidence.erw.base_weight, replication_modifier=0.5)

        return Claim(
            subject=str(raw.get("subject", "unknown"))[:100],
            predicate=predicate,
            object=str(raw.get("object", "unknown"))[:100],
            confidence=confidence,
            erw=erw,
            evidence_ids=[evidence.id],
            provenance=evidence.provenance,
            raw_text=raw_text,
            is_validated=False,
        )
