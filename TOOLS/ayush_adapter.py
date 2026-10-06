"""
AYUSH Ministry Retrieval Adapter — Playwright headless browser.

Retrieves regulations and documents from https://ayush.gov.in/ which is an
Angular Single Page Application. Standard HTTP requests return only the empty
``<app-root></app-root>`` shell, so Playwright is required for DOM rendering.

Key routes scraped:
  /whatsnew        — Notifications & what's new
  /ayurveda        — Ayurveda regulations & info
  /qualitystandard — Quality standards
  /schemes         — Government schemes
"""
import asyncio
import logging
import re
from typing import Optional

from .base_adapter import RetrievalAdapter, RetrievalResult

logger = logging.getLogger(__name__)

BASE_URL = "https://ayush.gov.in"

# Content routes documented in DATA_SOURCES/AYUSH/ayush_scraping_guide.md
CONTENT_ROUTES = {
    "whatsnew": {
        "path": "/whatsnew",
        "label": "Notifications & What's New",
    },
    "ayurveda": {
        "path": "/ayurveda",
        "label": "Ayurveda Regulations",
    },
    "qualitystandard": {
        "path": "/qualitystandard",
        "label": "Quality Standards",
    },
    "schemes": {
        "path": "/schemes",
        "label": "Schemes",
    },
    "tenders": {
        "path": "/tenders",
        "label": "Tenders",
    },
}

# Mapping of query keywords to relevant routes
KEYWORD_ROUTE_MAP = {
    "notification": ["whatsnew"],
    "new": ["whatsnew"],
    "circular": ["whatsnew"],
    "ayurveda": ["ayurveda", "qualitystandard"],
    "regulation": ["ayurveda", "qualitystandard"],
    "guideline": ["ayurveda", "qualitystandard"],
    "quality": ["qualitystandard"],
    "standard": ["qualitystandard"],
    "scheme": ["schemes"],
    "mission": ["schemes"],
    "tender": ["tenders"],
    "procurement": ["tenders"],
}


class AyushRetrievalAdapter(RetrievalAdapter):
    """Retrieve AYUSH regulations via Playwright (Angular SPA scraping)."""

    SOURCE_NAME = "AYUSH"
    PLAYWRIGHT_TIMEOUT = 30_000  # 30 seconds for Angular to render

    # ── Public interface ─────────────────────────────────────
    def retrieve(self, query: str, jurisdiction: str) -> RetrievalResult:
        """Scrape AYUSH website for documents matching *query*."""
        try:
            return self._retry(self._do_retrieve, query, jurisdiction)
        except Exception as exc:
            return self._error(query, jurisdiction, str(exc))

    # ── Internal logic ───────────────────────────────────────
    def _do_retrieve(self, query: str, jurisdiction: str) -> RetrievalResult:
        """Determine relevant routes from the query, then scrape them."""
        routes = self._select_routes(query)
        # Run the async scraping in a sync context
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an existing event loop (e.g. FastAPI)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run, self._scrape_routes(routes, query)
                ).result(timeout=60)
        else:
            result = asyncio.run(self._scrape_routes(routes, query))

        documents, text_parts, errors = result

        if not documents and errors:
            return self._error(
                query, jurisdiction,
                f"All routes failed: {'; '.join(errors)}"
            )

        if not documents:
            return self._partial(
                query, jurisdiction,
                documents=[],
                text=f"No documents found on AYUSH website for '{query}'.",
                error="No matching documents found",
            )

        summary = (
            f"[AYUSH] Found {len(documents)} document(s) "
            f"related to '{query}':\n\n" + "\n\n".join(text_parts)
        )

        if errors:
            return self._partial(
                query, jurisdiction, documents, summary,
                "; ".join(errors),
            )
        return self._ok(query, jurisdiction, documents, summary)

    async def _scrape_routes(self, routes: list, query: str):
        """Async: launch Playwright, scrape each route, return results."""
        from playwright.async_api import async_playwright

        all_documents = []
        all_text_parts = []
        errors = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                for route_key in routes:
                    route = CONTENT_ROUTES[route_key]
                    url = f"{BASE_URL}{route['path']}"
                    label = route["label"]
                    try:
                        docs, texts = await self._scrape_single_page(
                            browser, url, label, query
                        )
                        all_documents.extend(docs)
                        all_text_parts.extend(texts)
                    except Exception as exc:
                        errors.append(f"{label}: {exc}")
                        logger.warning("Failed to scrape %s: %s", url, exc)
            finally:
                await browser.close()

        return all_documents, all_text_parts, errors

    async def _scrape_single_page(self, browser, url: str,
                                  section_label: str, query: str):
        """Scrape a single Angular-rendered page for links and text."""
        page = await browser.new_page()
        try:
            logger.info("Navigating to %s ...", url)
            await page.goto(url, wait_until="networkidle",
                            timeout=self.PLAYWRIGHT_TIMEOUT)

            # Wait for Angular rendering
            await page.wait_for_timeout(2000)

            documents = []
            text_parts = []

            # Extract PDF links
            pdf_links = await page.locator("a[href$='.pdf']").all()
            for link in pdf_links:
                try:
                    title = (await link.inner_text()).strip()
                    href = await link.get_attribute("href")
                    if href:
                        if href.startswith("/"):
                            href = f"{BASE_URL}{href}"
                        doc = {
                            "title": title or self._title_from_url(href),
                            "url": href,
                            "type": "pdf",
                            "section": section_label,
                        }
                        documents.append(doc)
                        text_parts.append(
                            f"- {doc['title']}\n  URL: {doc['url']}\n"
                            f"  Section: {section_label}"
                        )
                except Exception:
                    continue

            # Extract page heading and body text for context
            page_text = await page.locator("body").inner_text()
            # Filter relevant snippets containing query keywords
            query_words = [w.lower() for w in query.split() if len(w) > 2]
            relevant_lines = []
            for line in page_text.split("\n"):
                line = line.strip()
                if not line or len(line) < 10:
                    continue
                if any(w in line.lower() for w in query_words):
                    relevant_lines.append(line)

            if relevant_lines and not documents:
                # No PDFs found but there is relevant text content
                snippet = "\n".join(relevant_lines[:10])
                text_parts.append(
                    f"- Text content from {section_label}:\n  {snippet}"
                )
                documents.append({
                    "title": f"{section_label} — text content",
                    "url": url,
                    "type": "html",
                    "section": section_label,
                    "snippet": snippet[:500],
                })

            return documents, text_parts
        finally:
            await page.close()

    def _select_routes(self, query: str) -> list:
        """Pick the most relevant routes based on query keywords."""
        query_lower = query.lower()
        matched_routes = set()

        for keyword, routes in KEYWORD_ROUTE_MAP.items():
            if keyword in query_lower:
                matched_routes.update(routes)

        # Default: scrape the two most general pages
        if not matched_routes:
            matched_routes = {"whatsnew", "ayurveda"}

        return list(matched_routes)[:3]  # Cap at 3 routes

    @staticmethod
    def _title_from_url(url: str) -> str:
        """Extract readable title from a PDF URL."""
        filename = url.rsplit("/", 1)[-1] if "/" in url else url
        name = re.sub(r"\.pdf$", "", filename, flags=re.I)
        return name.replace("_", " ").replace("-", " ").strip() or "Document"
