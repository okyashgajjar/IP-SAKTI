"""
WIPO Lex Retrieval Adapter — Playwright headless browser (Shadow DOM).

Retrieves international IP laws from https://wipolex.wipo.int/ which uses
custom WIPO Web Components with Shadow DOM encapsulation. Direct HTTP requests
return a CloudFront 404 page, so a full headless browser is mandatory.

Key routes:
  /en/main/legislation — Legislation search
  /en/main/treaties    — Treaties search
"""
import asyncio
import logging
import re
import time

from .base_adapter import RetrievalAdapter, RetrievalResult

logger = logging.getLogger(__name__)

BASE_URL = "https://wipolex.wipo.int"

# Country code defaults
DEFAULT_COUNTRY = "IN"  # India

# Subject codes from DATA_SOURCES/IP_COUNTRY/wipolex_scraping_details.md
SUBJECT_CODES = {
    "patent": "1",
    "trademark": "4",
    "copyright": "11",
    "industrial design": "7",
    "geographical indication": "10",
    "trade secret": "12",
}


class WipoLexRetrievalAdapter(RetrievalAdapter):
    """Retrieve international IP laws from WIPO Lex via Playwright."""

    SOURCE_NAME = "WIPO_LEX"
    PLAYWRIGHT_TIMEOUT = 40_000  # WIPO can be slow behind CloudFront

    # ── Public interface ─────────────────────────────────────
    def retrieve(self, query: str, jurisdiction: str) -> RetrievalResult:
        """Search WIPO Lex for IP legislation matching *query*."""
        try:
            return self._retry(self._do_retrieve, query, jurisdiction)
        except Exception as exc:
            return self._error(query, jurisdiction, str(exc))

    # ── Internal logic ───────────────────────────────────────
    def _do_retrieve(self, query: str, jurisdiction: str) -> RetrievalResult:
        """Run the headless search on WIPO Lex."""
        # Map jurisdiction to ISO country code
        country_code = self._jurisdiction_to_country(jurisdiction)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run,
                    self._search_legislation(query, country_code),
                ).result(timeout=90)
        else:
            result = asyncio.run(
                self._search_legislation(query, country_code)
            )

        documents, text_parts, error = result

        if error and not documents:
            return self._error(query, jurisdiction, error)

        if not documents:
            return self._partial(
                query, jurisdiction,
                documents=[],
                text=(
                    f"No IP legislation found on WIPO Lex for '{query}' "
                    f"(country: {country_code})."
                ),
                error="No results from WIPO Lex search",
            )

        summary = (
            f"[WIPO_LEX] Found {len(documents)} IP legislation item(s) "
            f"for '{query}' (country: {country_code}):\n\n"
            + "\n\n".join(text_parts)
        )

        if error:
            return self._partial(
                query, jurisdiction, documents, summary, error
            )
        return self._ok(query, jurisdiction, documents, summary)

    async def _search_legislation(self, query: str, country_code: str):
        """Async: launch Playwright, navigate to WIPO Lex, execute search."""
        from playwright.async_api import async_playwright

        documents = []
        text_parts = []
        error = ""

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()

                # Navigate to the legislation search page
                search_url = f"{BASE_URL}/en/main/legislation"
                logger.info("Navigating to %s ...", search_url)

                await page.goto(
                    search_url, wait_until="networkidle",
                    timeout=self.PLAYWRIGHT_TIMEOUT,
                )
                await page.wait_for_timeout(3000)

                # Inject search parameters via JavaScript
                # (Shadow DOM components require JS execution)
                search_js = f"""
                    (function() {{
                        // Try to populate keyword field
                        var keywordInput = document.querySelector(
                            'wu-input-text#keywords, input#keywords, '
                            + '[name="keywords"], input[placeholder*="keyword"]'
                        );
                        if (keywordInput) {{
                            keywordInput.value = '{query}';
                            keywordInput.dispatchEvent(
                                new Event('input', {{bubbles: true}})
                            );
                        }}

                        // Try to populate country field
                        var countryInput = document.querySelector(
                            'wu-input-text#countriesOrgs, '
                            + 'select#countriesOrgs, '
                            + '[name="countriesOrgs"]'
                        );
                        if (countryInput) {{
                            countryInput.value = '{country_code}';
                            countryInput.dispatchEvent(
                                new Event('change', {{bubbles: true}})
                            );
                        }}

                        // Try to trigger search
                        var searchBtn = document.querySelector(
                            'wu-button#searchBtn, button#searchBtn, '
                            + 'button[type="submit"], .search-btn'
                        );
                        if (searchBtn) {{
                            searchBtn.removeAttribute('disabled');
                            searchBtn.click();
                            return 'search_triggered';
                        }}
                        return 'no_button_found';
                    }})()
                """

                search_result = await page.evaluate(search_js)
                logger.info("Search JS result: %s", search_result)

                # Wait for results to load
                await page.wait_for_timeout(5000)

                # Try to extract results from the rendered page
                # Strategy 1: Look for result links / table rows
                result_links = await page.locator(
                    "a[href*='legislation'], a[href*='text'], "
                    "table.results a, .result-item a, "
                    ".search-results a"
                ).all()

                for link in result_links:
                    try:
                        title = (await link.inner_text()).strip()
                        href = await link.get_attribute("href")
                        if not title or not href:
                            continue
                        if href.startswith("/"):
                            href = f"{BASE_URL}{href}"

                        doc = {
                            "title": title,
                            "url": href,
                            "type": "legislation",
                            "country": country_code,
                        }
                        if not any(d["url"] == doc["url"]
                                   for d in documents):
                            documents.append(doc)
                            text_parts.append(
                                f"- {title}\n  URL: {href}"
                            )
                    except Exception:
                        continue

                # Strategy 2: Extract any visible text from result tables
                if not documents:
                    body_text = await page.locator("body").inner_text()
                    query_words = [
                        w.lower() for w in query.split() if len(w) > 2
                    ]
                    relevant_lines = []
                    for line in body_text.split("\n"):
                        line = line.strip()
                        if len(line) < 10:
                            continue
                        if any(w in line.lower() for w in query_words):
                            relevant_lines.append(line)

                    if relevant_lines:
                        snippet = "\n".join(relevant_lines[:15])
                        documents.append({
                            "title": f"WIPO Lex results for '{query}'",
                            "url": search_url,
                            "type": "html",
                            "country": country_code,
                            "snippet": snippet[:500],
                        })
                        text_parts.append(
                            f"- WIPO Lex text content:\n  {snippet[:300]}"
                        )

                await page.close()

            except Exception as exc:
                error = str(exc)
                logger.error("WIPO Lex scraping failed: %s", exc)
            finally:
                await browser.close()

        return documents, text_parts, error

    @staticmethod
    def _jurisdiction_to_country(jurisdiction: str) -> str:
        """Map jurisdiction string to ISO 2-letter country code."""
        mapping = {
            "IN": "IN",
            "US": "US",
            "EU": "EU",
            "WIPO": "",  # Global / all countries
            "UK": "GB",
            "JP": "JP",
            "CN": "CN",
        }
        return mapping.get(jurisdiction.upper(), jurisdiction.upper()[:2])
