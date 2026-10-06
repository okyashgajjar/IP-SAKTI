"""
Base Retrieval Adapter — abstract interface for all data-source connectors.

Every concrete adapter MUST return a ``RetrievalResult`` dict so that
downstream pipeline nodes (Evidence Reasoner, Citation Validator, etc.)
can consume evidence in a uniform schema.
"""
from abc import ABC, abstractmethod
from typing import TypedDict
import logging
import time

logger = logging.getLogger(__name__)


class RetrievalResult(TypedDict):
    """Standardized return type for every adapter."""
    source: str          # e.g. "AYUSH", "FSSAI", "INDIA_CODE", …
    query: str           # the original query echoed back
    jurisdiction: str    # e.g. "IN", "US", "WIPO"
    status: str          # "ok" | "partial" | "error" | "unavailable"
    documents: list      # list of dicts: {title, url, snippet?, type?}
    text: str            # human-readable summary / extracted text
    error: str           # empty string when no error


class RetrievalAdapter(ABC):
    """Abstract base class for all data-source retrieval adapters."""

    # ── Overridable defaults ─────────────────────────────────
    SOURCE_NAME: str = "UNKNOWN"
    REQUEST_TIMEOUT: int = 20        # seconds for HTTP requests
    PLAYWRIGHT_TIMEOUT: int = 30_000 # milliseconds for Playwright navigation
    MAX_RETRIES: int = 2
    RETRY_DELAY: float = 1.0        # seconds between retries

    # ── Concrete helpers ─────────────────────────────────────
    def _ok(self, query: str, jurisdiction: str,
            documents: list, text: str) -> RetrievalResult:
        """Convenience: build a successful result."""
        return RetrievalResult(
            source=self.SOURCE_NAME,
            query=query,
            jurisdiction=jurisdiction,
            status="ok",
            documents=documents,
            text=text,
            error="",
        )

    def _partial(self, query: str, jurisdiction: str,
                 documents: list, text: str,
                 error: str) -> RetrievalResult:
        """Convenience: build a partial-success result."""
        return RetrievalResult(
            source=self.SOURCE_NAME,
            query=query,
            jurisdiction=jurisdiction,
            status="partial",
            documents=documents,
            text=text,
            error=error,
        )

    def _error(self, query: str, jurisdiction: str,
               error: str) -> RetrievalResult:
        """Convenience: build an error result with graceful degradation."""
        logger.error("[%s] Retrieval failed: %s", self.SOURCE_NAME, error)
        return RetrievalResult(
            source=self.SOURCE_NAME,
            query=query,
            jurisdiction=jurisdiction,
            status="error",
            documents=[],
            text=f"Data source unavailable: {error}",
            error=error,
        )

    def _retry(self, func, *args, **kwargs):
        """Execute *func* with exponential-backoff retries."""
        last_exc = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                delay = self.RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "[%s] Attempt %d/%d failed: %s — retrying in %.1fs",
                    self.SOURCE_NAME, attempt, self.MAX_RETRIES, exc, delay,
                )
                time.sleep(delay)
        raise last_exc  # type: ignore[misc]

    # ── Abstract contract ────────────────────────────────────
    @abstractmethod
    def retrieve(self, query: str, jurisdiction: str) -> RetrievalResult:
        """Retrieve evidence based on *query* and *jurisdiction*.

        Must return a ``RetrievalResult`` dict — never raise to the caller
        in production; use ``_error()`` for graceful degradation instead.
        """
        ...
