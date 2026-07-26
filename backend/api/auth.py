"""API Authentication — Phase 3 Production Feature.

Implements API key authentication via X-API-Key header.
Keys are configurable via environment variables.

Public endpoints (no auth): /api/v1/health, /docs, /redoc, /openapi.json

Reference: Phase 3 — User authentication
"""
from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

# Header name for API key
_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# Public paths that bypass authentication
_PUBLIC_PATHS: set[str] = {
    "/api/v1/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/",
}


def _get_valid_api_keys() -> set[str]:
    """Load valid API keys from environment.

    Supports multiple keys via comma-separated CYNTHERA_API_KEYS env var.
    Falls back to CYNTHERA_API_KEY (single key).
    If neither is set, returns a development key (logs a warning).
    """
    multi_key = os.environ.get("CYNTHERA_API_KEYS", "")
    if multi_key:
        keys = {k.strip() for k in multi_key.split(",") if k.strip()}
        if keys:
            return keys

    single_key = os.environ.get("CYNTHERA_API_KEY", "")
    if single_key:
        return {single_key}

    # Development fallback
    dev_key = "dev-key-cynthera-2024"
    logger.warning(
        "api_key_fallback_active",
        extra={
            "message": (
                "No CYNTHERA_API_KEY set. Using development fallback key. "
                "Set CYNTHERA_API_KEY in your .env for production."
            )
        },
    )
    return {dev_key}


async def verify_api_key(
    api_key: Annotated[str | None, Security(_API_KEY_HEADER)],
) -> str:
    """FastAPI dependency that validates the X-API-Key header.

    Args:
        api_key: API key from the X-API-Key header.

    Returns:
        The validated API key string.

    Raises:
        401: If API key is missing.
        403: If API key is invalid.
    """
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    valid_keys = _get_valid_api_keys()
    if api_key not in valid_keys:
        logger.warning("invalid_api_key_attempt", extra={"key_prefix": api_key[:8]})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )

    return api_key


# Dependency alias for convenience
AuthDep = Annotated[str, Depends(verify_api_key)]
