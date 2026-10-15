"""
AYUSH Ministry Retrieval Adapter — Playwright headless browser.

Retrieves regulations, guidelines, and documents from https://ayush.gov.in/
which is an Angular Single Page Application.

Key content rendered on the main portal:
  - Acts & Rules (NCISM Act, NCH Act, ITRA Act, etc.)
  - What's New & Circulars (clinical guidelines, export advisories, notifications)
  - Quality Standards (benchmark rates, annexures)
  - National Schemes (Ayurswasthya, Ayurgyan, Drug Quality & Manufacturing)
"""
import asyncio
import logging
import re
from typing import Optional

from .base_adapter import RetrievalAdapter, RetrievalResult

logger = logging.getLogger(__name__)

BASE_URL = "https://ayush.gov.in"

# Regulatory stop words to prevent false-positive matching
STOP_WORDS = {
    "the", "and", "for", "from", "with", "that", "this", "are",
    "was", "has", "had", "have", "been", "not", "but", "its",
    "all", "any", "can", "may", "will", "shall", "under", "into",
    "ayush", "ministry", "government", "india", "indian", "what",
    "how", "which", "about", "our", "per", "via",
}

# 60-second in-memory cache to avoid redundant browser launches for multi-query batches
_PORTAL_CACHE = {
    "data": None,
    "timestamp": 0.0,
}


class AyushRetrievalAdapter(RetrievalAdapter):
    """Retrieve AYUSH regulations via Playwright (Angular SPA scraping)."""

    SOURCE_NAME = "AYUSH"
    PLAYWRIGHT_TIMEOUT = 15_000  # 15 seconds max (domcontentloaded)
    MAX_RETRIES = 1             # Don't double timeout on slow gov servers

    # ── Public interface ─────────────────────────────────────
    def retrieve(self, query: str, jurisdiction: str) -> RetrievalResult:
        """Scrape AYUSH website for documents matching *query*."""
        try:
            return self._retry(self._do_retrieve, query, jurisdiction)
        except Exception as exc:
            return self._error(query, jurisdiction, str(exc))

    # ── Internal logic ───────────────────────────────────────
    def _do_retrieve(self, query: str, jurisdiction: str) -> RetrievalResult:
        """Scrape the AYUSH portal for documents and text matching the query."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run, self._scrape_portal(query)
                ).result(timeout=30)
        else:
            result = asyncio.run(self._scrape_portal(query))

        documents, text_parts, errors = result

        if not documents and errors:
            return self._error(
                query, jurisdiction,
                f"Portal scrape failed: {'; '.join(errors)}"
            )

        if not documents:
            return self._partial(
                query, jurisdiction,
                documents=[],
                text=f"No matching documents found on AYUSH portal for '{query}'.",
                error="No matching documents found",
            )

        summary = (
            f"[AYUSH] Found {len(documents)} document(s) / reference(s) "
            f"related to '{query}':\n\n" + "\n\n".join(text_parts)
        )

        if errors:
            return self._partial(
                query, jurisdiction, documents, summary,
                "; ".join(errors),
            )
        return self._ok(query, jurisdiction, documents, summary)

    async def _scrape_portal(self, query: str):
        """Async: load portal DOM (or use 60s cache), extract matching docs & text."""
        import time
        from playwright.async_api import async_playwright

        documents = []
        text_parts = []
        errors = []
        query_keywords = self._build_relevance_keywords(query)

        # Check 60-second in-memory cache
        now = time.time()
        if _PORTAL_CACHE["data"] is not None and (now - _PORTAL_CACHE["timestamp"]) < 60:
            data = _PORTAL_CACHE["data"]
        else:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page()
                    try:
                        logger.info("Navigating to %s ...", BASE_URL)
                        await page.goto(BASE_URL + "/", wait_until="domcontentloaded",
                                        timeout=self.PLAYWRIGHT_TIMEOUT)
                        await page.wait_for_timeout(2000)

                        data = await page.evaluate('''() => {
                            const links = Array.from(document.querySelectorAll('a')).map(a => ({
                                href: a.href || '',
                                text: (a.innerText || '').trim().replace(/\\s+/g, ' ')
                            }));
                            const bodyText = document.body ? document.body.innerText : '';
                            return { links, bodyText };
                        }''')
                        _PORTAL_CACHE["data"] = data
                        _PORTAL_CACHE["timestamp"] = now
                    except Exception as exc:
                        errors.append(str(exc))
                        logger.warning("AYUSH scraping failed: %s", exc)
                        data = {"links": [], "bodyText": ""}
                    finally:
                        await page.close()
                finally:
                    await browser.close()

        raw_links = data.get("links", [])
        body_text = data.get("bodyText", "")

        # ── 1. Document Extraction & Scoring ──
        scored_docs = []
        seen_urls = set()

        for link in raw_links:
            href = link.get("href", "")
            title = link.get("text", "")
            if not href or href in seen_urls:
                continue

            # Check if this link points to a document or regulatory page
            href_lower = href.lower()
            is_doc = any(ext in href_lower for ext in [
                ".pdf", ".doc", ".docx", "/assets/pdf",
                "/schemes", "/ayushinindiapublications",
                "/ayushdomains", "ncism", "itra"
            ])

            if not is_doc:
                continue

            seen_urls.add(href)

            # Fix relative URLs if any
            if href.startswith("/"):
                href = f"{BASE_URL}{href}"

            # Score relevance
            combined = f"{title} {href}".lower()
            score = self._score_relevance(combined, title.lower(), query_keywords)
            if score > 0:
                clean_title = title or self._title_from_url(href)
                scored_docs.append((score, {
                    "title": clean_title,
                    "url": href,
                    "type": "pdf" if ".pdf" in href_lower else "web",
                    "section": "AYUSH Official Portal",
                }))

        # Sort by score descending and take top 5
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        for _, doc in scored_docs[:5]:
            documents.append(doc)
            text_parts.append(
                f"- {doc['title']}\n  URL: {doc['url']}\n  Section: {doc['section']}"
            )

        # ── 2. Page Text Context Extraction ──
        lines = [line.strip() for line in body_text.split("\n") if len(line.strip()) > 15]
        relevant_lines = []
        for line in lines:
            if self._score_relevance(line.lower(), "", query_keywords) > 0:
                if line not in relevant_lines:
                    relevant_lines.append(line)

        if relevant_lines:
            snippet = "\n".join(relevant_lines[:8])
            text_parts.append(
                f"- Context from AYUSH Portal:\n  {snippet}"
            )
            if not documents:
                # If no direct file link matched, return text content
                documents.append({
                    "title": "AYUSH Ministry Portal Announcements & Guidelines",
                    "url": BASE_URL,
                    "type": "html",
                    "section": "AYUSH Official Portal",
                    "snippet": snippet[:500],
                })

        return documents, text_parts, errors

    @classmethod
    def _build_relevance_keywords(cls, query: str) -> list[str]:
        """Extract meaningful keywords from query for relevance matching."""
        words = re.split(r"[\s/,\-()]+", query.lower())
        return [w for w in words if len(w) > 2 and w not in STOP_WORDS]

    @staticmethod
    def _score_relevance(text: str, title: str, keywords: list[str]) -> int:
        """Calculate relevance score based on keyword matches."""
        score = 0
        for kw in keywords:
            if kw in title:
                score += 3  # Higher weight for title match
            elif kw in text:
                score += 1
        return score

    @staticmethod
    def _title_from_url(url: str) -> str:
        """Extract readable title from a PDF URL."""
        filename = url.rsplit("/", 1)[-1] if "/" in url else url
        name = re.sub(r"\.pdf$", "", filename, flags=re.I)
        return name.replace("_", " ").replace("-", " ").strip() or "Document"
