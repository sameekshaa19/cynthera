"""BaseConnector — abstract base class for all source connectors.

Reference: 08_IMPLEMENTATION_GUIDE.md §5.5, 03_RETRIEVAL_SPECIFICATION.md
"""
from __future__ import annotations

import abc
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class BaseConnector(abc.ABC):
    """Abstract base class that all Source connectors must extend.

    Enforces:
    - Async HTTP calls via httpx
    - Retry logic via tenacity (configured in subclass)
    - Structured error handling: httpx errors re-raised as domain exceptions
    - No normalization or reasoning in this layer

    Subclasses must implement:
        - source_name (class attribute)
        - base_url (class attribute)
        - fetch() method
    """

    source_name: str = "base"
    base_url: str = ""
    timeout_seconds: float = 30.0

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the connector with an optional API key.

        Args:
            api_key: Optional API key for authenticated endpoints.
        """
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BaseConnector":
        """Open the async HTTP client context."""
        self._client = httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers=self._build_headers(),
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Close the async HTTP client context."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _build_headers(self) -> dict[str, str]:
        """Build default request headers. Override in subclass for auth headers."""
        headers = {"Accept": "application/json", "User-Agent": "CYNTHERA/1.0"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    @abc.abstractmethod
    async def fetch(self, **kwargs: Any) -> dict[str, Any]:
        """Fetch raw data from the source API.

        Args:
            **kwargs: Source-specific query parameters.

        Returns:
            Raw JSON payload as a Python dict.

        Raises:
            SourceUnavailableError: If all retries are exhausted.
        """
        raise NotImplementedError

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GET request and return parsed JSON.

        Args:
            url: Full URL to request.
            params: Optional query parameters.

        Returns:
            Parsed JSON response as dict.

        Raises:
            SourceUnavailableError: If the request fails after retries.
        """
        from backend.core.exceptions import SourceUnavailableError

        if not self._client:
            raise RuntimeError(
                f"{self.__class__.__name__} must be used as an async context manager."
            )
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "http_error",
                extra={
                    "source": self.source_name,
                    "url": url,
                    "status_code": exc.response.status_code,
                },
            )
            raise SourceUnavailableError(
                source_name=self.source_name,
                retry_count=0,
            ) from exc
        except httpx.RequestError as exc:
            logger.error(
                "request_error",
                extra={"source": self.source_name, "url": url, "error": str(exc)},
            )
            raise SourceUnavailableError(
                source_name=self.source_name,
                retry_count=0,
            ) from exc
