"""
FSSAI Retrieval Adapter — Playwright headless browser + requests.

Retrieves food safety regulations from https://fssai.gov.in/ which is a
React SPA (Vite-built). Standard HTTP requests return ``<div id="root"></div>``,
so Playwright is required for DOM rendering. Legacy PDFs on
``stg-old.fssai.gov.in`` can be downloaded via standard HTTP.

Key routes:
  /food-law/regulations    — FSS Regulations
  /food-law/notifications  — Gazette Notifications
  /food-law/advisories     — Advisories and Orders
  /food-law/act-2006       — The main Act
  /food-law/rules-2011     — FSS Rules
"""
import asyncio
import logging
import re

import requests as http_requests

from .base_adapter import RetrievalAdapter, RetrievalResult

logger = logging.getLogger(__name__)

BASE_URL = "https://fssai.gov.in"

# Routes documented in DATA_SOURCES/FSSAI/fssai_scraping_guide.md
CONTENT_ROUTES = {
    "regulations": {
        "path": "/food-law/regulations",
        "label": "FSS Regulations",
    },
    "notifications": {
        "path": "/food-law/notifications",
        "label": "Gazette Notifications",
    },
    "advisories": {
        "path": "/food-law/advisories",
        "label": "Advisories & Orders",
    },
    "act": {
        "path": "/food-law/act-2006",
        "label": "Food Safety Act 2006",
    },
    "rules": {
        "path": "/food-law/rules-2011",
        "label": "FSS Rules 2011",
    },
}

KEYWORD_ROUTE_MAP = {
    "regulation": ["regulations"],
    "notification": ["notifications"],
    "gazette": ["notifications"],
    "advisory": ["advisories"],
    "order": ["advisories"],
    "act": ["act"],
    "rule": ["rules"],
    "aahara": ["regulations", "notifications"],
    "ayurveda": ["regulations", "notifications"],
    "labeling": ["regulations"],
    "label": ["regulations"],
    "packaging": ["regulations"],
    "food": ["regulations", "act"],
    "safety": ["act", "rules"],
    "license": ["rules"],
    "hygiene": ["rules"],
}


class FssaiRetrievalAdapter(RetrievalAdapter):
    """Retrieve FSSAI food-safety regulations via Playwright (React SPA)."""

    SOURCE_NAME = "FSSAI"
    PLAYWRIGHT_TIMEOUT = 30_000

    # ── Public interface ─────────────────────────────────────
    def retrieve(self, query: str, jurisdiction: str) -> RetrievalResult:
        """Scrape FSSAI website for documents matching *query*."""
        try:
            return self._retry(self._do_retrieve, query, jurisdiction)
        except Exception as exc:
            return self._error(query, jurisdiction, str(exc))

    # ── Internal logic ───────────────────────────────────────
    def _do_retrieve(self, query: str, jurisdiction: str) -> RetrievalResult:
        """Determine relevant routes from query, then scrape them."""
        routes = self._select_routes(query)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
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
                text=f"No documents found on FSSAI website for '{query}'.",
                error="No matching documents found",
            )

        summary = (
            f"[FSSAI] Found {len(documents)} document(s) "
            f"related to '{query}':\n\n" + "\n\n".join(text_parts)
        )

        if errors:
            return self._partial(
                query, jurisdiction, documents, summary,
                "; ".join(errors),
            )
        return self._ok(query, jurisdiction, documents, summary)

    async def _scrape_routes(self, routes: list, query: str):
        """Async: launch Playwright, scrape each route."""
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
        """Scrape a single React-rendered page for document links."""
        page = await browser.new_page()
        try:
            logger.info("Navigating to %s ...", url)
            await page.goto(url, wait_until="networkidle",
                            timeout=self.PLAYWRIGHT_TIMEOUT)

            # Let React hydrate / render
            await page.wait_for_timeout(2000)

            documents = []
            text_parts = []

            # Extract PDF links from the rendered DOM
            all_links = await page.locator("a[href]").all()
            for link in all_links:
                try:
                    href = await link.get_attribute("href")
                    if not href:
                        continue

                    # Filter for PDF documents and gazette links
                    is_pdf = ".pdf" in href.lower()
                    is_gazette = "gazette" in href.lower() or "view-gazette" in href.lower()

                    if not (is_pdf or is_gazette):
                        continue

                    title = (await link.inner_text()).strip()
                    if not title:
                        title = self._title_from_url(href)

                    # Build absolute URL
                    if href.startswith("/"):
                        href = f"{BASE_URL}{href}"
                    elif not href.startswith("http"):
                        href = f"{BASE_URL}/{href}"

                    doc = {
                        "title": title,
                        "url": href,
                        "type": "pdf" if is_pdf else "gazette",
                        "section": section_label,
                    }

                    # Deduplicate
                    if not any(d["url"] == doc["url"] for d in documents):
                        documents.append(doc)
                        text_parts.append(
                            f"- {doc['title']}\n  URL: {doc['url']}\n"
                            f"  Section: {section_label}"
                        )
                except Exception:
                    continue

            # Also extract visible text content for context
            page_text = await page.locator("body").inner_text()
            query_words = [w.lower() for w in query.split() if len(w) > 2]
            relevant_lines = []
            for line in page_text.split("\n"):
                line = line.strip()
                if not line or len(line) < 10:
                    continue
                if any(w in line.lower() for w in query_words):
                    relevant_lines.append(line)

            if relevant_lines and not documents:
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
        """Pick the most relevant FSSAI routes based on query keywords."""
        query_lower = query.lower()
        matched_routes = set()

        for keyword, routes in KEYWORD_ROUTE_MAP.items():
            if keyword in query_lower:
                matched_routes.update(routes)

        if not matched_routes:
            matched_routes = {"regulations", "notifications"}

        return list(matched_routes)[:3]

    @staticmethod
    def _title_from_url(url: str) -> str:
        """Extract readable title from a URL."""
        filename = url.rsplit("/", 1)[-1] if "/" in url else url
        name = re.sub(r"\.(pdf|php|html?)$", "", filename, flags=re.I)
        return name.replace("_", " ").replace("-", " ").strip() or "Document"
