"""
NBA (National Biodiversity Authority) Retrieval Adapter.

Retrieves biodiversity regulations from https://www.nbaindia.nic.in/ using
standard HTTP requests + BeautifulSoup HTML parsing.

The NBA website is Drupal-based and server-renders its HTML, so no headless
browser is needed — a simple GET + parse approach works reliably.
"""
import logging
import re

import requests
from bs4 import BeautifulSoup

from .base_adapter import RetrievalAdapter, RetrievalResult

logger = logging.getLogger(__name__)

BASE_URL = "https://www.nbaindia.nic.in"

# Key pages documented in DATA_SOURCES/NBA/nba_scraping_details.md
PAGES = {
    "rules": {
        "url": f"{BASE_URL}/acts-and-rules/rules",
        "label": "Acts & Rules",
    },
    "notifications": {
        "url": f"{BASE_URL}/public-information/notification-guidelines",
        "label": "Notification & Guidelines",
    },
    "home": {
        "url": BASE_URL,
        "label": "Homepage Circulars",
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


class NbaRetrievalAdapter(RetrievalAdapter):
    """Retrieve biodiversity regulations from the NBA India website."""

    SOURCE_NAME = "NBA"
    REQUEST_TIMEOUT = 20

    # ── Public interface ─────────────────────────────────────
    def retrieve(self, query: str, jurisdiction: str) -> RetrievalResult:
        """Scrape NBA website for documents matching *query*."""
        try:
            return self._retry(self._do_retrieve, query, jurisdiction)
        except Exception as exc:
            return self._error(query, jurisdiction, str(exc))

    # ── Internal logic ───────────────────────────────────────
    def _do_retrieve(self, query: str, jurisdiction: str) -> RetrievalResult:
        """Fetch and parse all key NBA pages for relevant documents."""
        all_documents = []
        errors = []

        for page_key, page_info in PAGES.items():
            try:
                docs = self._scrape_page(page_info["url"], page_info["label"])
                all_documents.extend(docs)
            except Exception as exc:
                errors.append(f"{page_info['label']}: {exc}")
                logger.warning("Failed to scrape %s: %s", page_key, exc)

        # Filter by query keywords (case-insensitive)
        query_lower = query.lower()
        query_words = [w for w in query_lower.split() if len(w) > 2]

        if query_words:
            filtered = [
                doc for doc in all_documents
                if any(
                    word in doc.get("title", "").lower()
                    for word in query_words
                )
            ]
            # If no keyword matches, return all documents (broad match)
            if filtered:
                all_documents = filtered

        if not all_documents and errors:
            return self._error(
                query, jurisdiction,
                f"All pages failed: {'; '.join(errors)}"
            )

        if not all_documents:
            return self._partial(
                query, jurisdiction,
                documents=[],
                text=f"No documents found on NBA website matching '{query}'.",
                error="No matching documents",
            )

        # Build text summary
        text_parts = []
        for doc in all_documents[:15]:  # Cap summary to 15 items
            parts = [f"- {doc['title']}"]
            if doc.get("url"):
                parts.append(f"  URL: {doc['url']}")
            if doc.get("section"):
                parts.append(f"  Section: {doc['section']}")
            text_parts.append("\n".join(parts))

        status = "ok" if not errors else "partial"
        error_msg = "; ".join(errors) if errors else ""

        summary = (
            f"[NBA] Found {len(all_documents)} document(s) "
            f"related to '{query}':\n\n" + "\n\n".join(text_parts)
        )

        if status == "partial":
            return self._partial(
                query, jurisdiction, all_documents, summary, error_msg
            )
        return self._ok(query, jurisdiction, all_documents, summary)

    def _scrape_page(self, url: str, section_label: str) -> list:
        """Fetch a page and extract PDF document links."""
        resp = requests.get(url, headers=HEADERS, timeout=self.REQUEST_TIMEOUT)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        documents = []

        # Strategy 1: Find all download links (class="download-link")
        for link in soup.find_all("a", class_="download-link"):
            href = link.get("href", "")
            title = link.get_text(strip=True) or self._title_from_href(href)
            if href:
                documents.append({
                    "title": title,
                    "url": self._absolute_url(href),
                    "type": "pdf",
                    "section": section_label,
                })

        # Strategy 2: Find all links ending in .pdf
        for link in soup.find_all("a", href=re.compile(r"\.pdf", re.I)):
            href = link.get("href", "")
            abs_url = self._absolute_url(href)
            # Avoid duplicates
            if any(d["url"] == abs_url for d in documents):
                continue
            title = link.get_text(strip=True) or self._title_from_href(href)
            if href:
                documents.append({
                    "title": title,
                    "url": abs_url,
                    "type": "pdf",
                    "section": section_label,
                })

        # Strategy 3: Look inside doc-link class (homepage circulars)
        for link in soup.find_all("a", class_="doc-link"):
            href = link.get("href", "")
            abs_url = self._absolute_url(href)
            if any(d["url"] == abs_url for d in documents):
                continue
            title = link.get_text(strip=True) or self._title_from_href(href)
            if href:
                documents.append({
                    "title": title,
                    "url": abs_url,
                    "type": "document",
                    "section": section_label,
                })

        return documents

    def _absolute_url(self, href: str) -> str:
        """Convert a relative URL to absolute."""
        if href.startswith("http"):
            return href
        if href.startswith("/"):
            return f"{BASE_URL}{href}"
        return f"{BASE_URL}/{href}"

    @staticmethod
    def _title_from_href(href: str) -> str:
        """Extract a readable title from a file URL path."""
        filename = href.rsplit("/", 1)[-1] if "/" in href else href
        # Remove extension and replace underscores/hyphens with spaces
        name = re.sub(r"\.(pdf|docx?|xlsx?)$", "", filename, flags=re.I)
        return name.replace("_", " ").replace("-", " ").strip() or "Document"
