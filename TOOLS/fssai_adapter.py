"""
FSSAI Retrieval Adapter — Playwright headless browser.

Retrieves food safety regulations and Ayurveda Aahara rules from
https://fssai.gov.in/ which is a React SPA (Vite-built).

Key routes:
  /food-law/regulations    — FSS Regulations (Ayurvedic Aahara, Nutraceuticals, etc.)
  /food-law/notifications  — Gazette Notifications
  /food-law/advisories     — Advisories and Orders
  /food-law/act-2006       — The main Food Safety Act
  /food-law/rules-2011     — FSS Rules
"""
import asyncio
import logging
import re
from typing import Optional

from playwright.async_api import async_playwright

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
    "ayurvedic": ["regulations", "notifications"],
    "labeling": ["regulations"],
    "label": ["regulations"],
    "packaging": ["regulations"],
    "supplement": ["regulations"],
    "nutraceutical": ["regulations"],
    "herbal": ["regulations"],
    "capsule": ["regulations"],
    "food": ["regulations", "act"],
    "safety": ["act", "rules"],
    "license": ["rules", "regulations"],
}

# Generic words to exclude from relevance keywords so they don't match every PDF
STOP_WORDS = {
    "the", "and", "for", "from", "with", "that", "this", "are",
    "was", "has", "had", "have", "been", "not", "but", "its",
    "all", "any", "can", "may", "will", "shall", "under", "into",
    "fssai", "india", "indian", "what", "how", "which",
    "regulation", "regulations", "rule", "rules", "act", "acts",
    "order", "orders", "guideline", "guidelines", "document", "documents",
    "compendium", "corrigenda", "notification", "notifications", "gazette",
    "amendment", "amendments", "pdf", "html", "direction",
}

# 60-second in-memory cache per route to avoid redundant browser scrapes
_ROUTE_CACHE = {}


class FssaiRetrievalAdapter(RetrievalAdapter):
    """Retrieve FSSAI food-safety regulations via Playwright (React SPA)."""

    SOURCE_NAME = "FSSAI"
    PLAYWRIGHT_TIMEOUT = 15_000  # 15s timeout
    MAX_RETRIES = 1             # Don't double timeout on slow gov servers

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
                ).result(timeout=45)
        else:
            result = asyncio.run(self._scrape_routes(routes, query))

        documents, text_parts, errors = result

        if not documents and errors:
            return self._error(
                query, jurisdiction,
                f"FSSAI retrieval failed: {'; '.join(errors)}"
            )

        if not documents:
            return self._partial(
                query, jurisdiction,
                documents=[],
                text=f"No matching documents found on FSSAI website for '{query}'.",
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
        """Async: launch Playwright, scrape selected routes."""
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

        # Deduplicate documents by URL across routes
        unique_docs = []
        unique_texts = []
        seen_urls = set()
        for doc, txt in zip(all_documents, all_text_parts):
            u = doc.get("url")
            if u not in seen_urls:
                seen_urls.add(u)
                unique_docs.append(doc)
                unique_texts.append(txt)

        return unique_docs[:5], unique_texts[:5], errors

    async def _scrape_single_page(self, browser, url: str,
                                  section_label: str, query: str):
        """Scrape a single React-rendered page using fast evaluate and relevance ranking."""
        import time
        now = time.time()
        cached = _ROUTE_CACHE.get(url)
        if cached and (now - cached["timestamp"]) < 60:
            data = cached["data"]
        else:
            page = await browser.new_page()
            try:
                logger.info("Navigating to %s ...", url)
                await page.goto(url, wait_until="domcontentloaded",
                                timeout=self.PLAYWRIGHT_TIMEOUT)
                await page.wait_for_timeout(2000)

                # Fast evaluation of all links and body text in one JS call
                data = await page.evaluate('''() => {
                    const links = Array.from(document.querySelectorAll('a')).map(a => ({
                        href: a.href || '',
                        text: (a.innerText || '').trim().replace(/\\s+/g, ' ')
                    }));
                    const bodyText = document.body ? document.body.innerText : '';
                    return { links, bodyText };
                }''')
                _ROUTE_CACHE[url] = {"data": data, "timestamp": now}
            finally:
                await page.close()

        documents = []
        text_parts = []
        query_keywords = self._build_relevance_keywords(query)
        is_hindi_query = any("\u0900" <= ch <= "\u097F" for ch in query)

        raw_links = data.get("links", [])
        body_text = data.get("bodyText", "")

        # ── Score and filter PDF and gazette documents ──
        scored_docs = []
        for link in raw_links:
            href = link.get("href", "")
            title = link.get("text", "")
            if not href:
                continue

            href_lower = href.lower()
            is_pdf = ".pdf" in href_lower
            is_gazette = "gazette" in href_lower or "view-gazette" in href_lower
            if not (is_pdf or is_gazette):
                continue

            # Title resolution
            clean_title = title or self._title_from_url(href)

            # Penalize Hindi versions if query is in English
            if not is_hindi_query and ("hindi" in clean_title.lower() or "hindi" in href_lower):
                continue

            # Normalize URL
            if href.startswith("/"):
                href = f"{BASE_URL}{href}"

            score = self._score_relevance(clean_title.lower(), href_lower, query_keywords)
            if score > 0:
                scored_docs.append((score, {
                    "title": clean_title,
                    "url": href,
                    "type": "pdf" if is_pdf else "gazette",
                    "section": section_label,
                }))

        scored_docs.sort(key=lambda x: x[0], reverse=True)
        for _, doc in scored_docs[:5]:
            documents.append(doc)
            text_parts.append(
                f"- {doc['title']}\n  URL: {doc['url']}\n  Section: {section_label}"
            )

        # ── Extract page text context if no files matched ──
        if not documents and body_text:
            lines = [l.strip() for l in body_text.split("\n") if len(l.strip()) > 15]
            matched_lines = []
            for l in lines:
                if any(kw in l.lower() for kw in query_keywords):
                    if l not in matched_lines:
                        matched_lines.append(l)

            if matched_lines:
                snippet = "\n".join(matched_lines[:6])
                documents.append({
                    "title": f"{section_label} — text content",
                    "url": url,
                    "type": "html",
                    "section": section_label,
                    "snippet": snippet[:500],
                })
                text_parts.append(
                    f"- Context from {section_label}:\n  {snippet}"
                )

        return documents, text_parts

    def _select_routes(self, query: str) -> list:
        """Pick the most relevant FSSAI routes based on query keywords."""
        query_lower = query.lower()
        matched_routes = set()

        for keyword, routes in KEYWORD_ROUTE_MAP.items():
            if keyword in query_lower:
                matched_routes.update(routes)

        if not matched_routes:
            matched_routes = {"regulations", "notifications"}

        return list(matched_routes)[:2]  # Cap at 2 routes to keep fast

    @classmethod
    def _build_relevance_keywords(cls, query: str) -> list[str]:
        """Extract meaningful keywords from query for relevance matching."""
        words = re.split(r"[\s/,\-()]+", query.lower())
        return [w for w in words if len(w) > 2 and w not in STOP_WORDS]

    @staticmethod
    def _score_relevance(title: str, url: str, keywords: list[str]) -> int:
        """Score document relevance based on keyword occurrences in title and URL."""
        score = 0
        for kw in keywords:
            if kw in title:
                score += 3
            elif kw in url:
                score += 1
        return score

    @staticmethod
    def _title_from_url(url: str) -> str:
        """Extract readable title from a URL."""
        filename = url.rsplit("/", 1)[-1] if "/" in url else url
        name = re.sub(r"\.(pdf|php|html?)$", "", filename, flags=re.I)
        return name.replace("_", " ").replace("-", " ").strip() or "Document"
