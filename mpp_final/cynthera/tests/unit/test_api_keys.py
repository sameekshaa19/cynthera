"""Tests for API key sanitization helpers."""
from __future__ import annotations

from backend.core.utils.api_keys import (
    is_valid_gemini_key,
    is_valid_groq_key,
    sanitize_api_key,
)


def test_sanitize_rejects_env_template_placeholders():
    assert sanitize_api_key("your-ncbi-api-key-here") is None
    assert sanitize_api_key("your-groq-api-key-here") is None
    assert sanitize_api_key("gsk_your_groq_api_key_here") is None


def test_sanitize_accepts_realistic_keys():
    assert sanitize_api_key("gsk_realKey123") == "gsk_realKey123"
    assert sanitize_api_key("AIzaSyRealGeminiKey") == "AIzaSyRealGeminiKey"


def test_groq_and_gemini_validators():
    assert is_valid_groq_key("your-groq-api-key-here") is False
    assert is_valid_groq_key("gsk_abc123") is True
    assert is_valid_gemini_key("your-gemini-key-here") is False
    assert is_valid_gemini_key("AIzaSyabc123") is True
