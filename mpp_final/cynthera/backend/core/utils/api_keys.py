"""API key validation helpers — strip placeholder values from .env templates."""
from __future__ import annotations

_PLACEHOLDER_PREFIXES = (
    "your-",
    "your_",
    "gsk_your",
    "changeme",
    "replace-me",
    "replace_me",
    "xxx",
    "placeholder",
)
_PLACEHOLDER_SUFFIXES = ("-here", "_here")


def sanitize_api_key(key: str | None) -> str | None:
    """Return the key if it looks configured, else None.

    Template values copied from `.env.example` (e.g. ``your-ncbi-api-key-here``)
    must not be sent to external APIs — several providers return 400/401 when
    they receive a syntactically present but invalid key.
    """
    if key is None:
        return None
    key = key.strip()
    if not key:
        return None
    lower = key.lower()
    for prefix in _PLACEHOLDER_PREFIXES:
        if lower.startswith(prefix):
            return None
    for suffix in _PLACEHOLDER_SUFFIXES:
        if lower.endswith(suffix):
            return None
    return key


def is_valid_groq_key(key: str | None) -> bool:
    """True when the value is a real Groq API key (``gsk_…``)."""
    key = sanitize_api_key(key)
    return bool(key and key.startswith("gsk_"))


def is_valid_gemini_key(key: str | None) -> bool:
    """True when the value is a Google Gemini / AI Studio API key."""
    key = sanitize_api_key(key)
    return bool(key and key.startswith("AIza"))


def is_valid_openrouter_key(key: str | None) -> bool:
    """True when the value is an OpenRouter API key."""
    key = sanitize_api_key(key)
    return bool(key and key.startswith("sk-or-"))


def is_valid_edenai_key(key: str | None) -> bool:
    """True when the value looks like a configured EdenAI key."""
    key = sanitize_api_key(key)
    return bool(key and len(key) > 10)
