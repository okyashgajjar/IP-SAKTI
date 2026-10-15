"""
India Code Retrieval Adapter — DSpace REST API.

Retrieves legislation from https://indiacode.gov.in/ using its public
DSpace 7/9 REST API. No headless browser needed — pure JSON over HTTP.

API traversal:
  Communities (CENTRAL / State) → Collections (Acts, Rules, …)
  → Items (specific legislation) → metadata + PDF links
"""
import logging
import re
import requests

from .base_adapter import RetrievalAdapter, RetrievalResult

logger = logging.getLogger(__name__)

BASE_URL = "https://indiacode.gov.in/server/api"

# Pre-verified UUIDs from DATA_SOURCES testing
CENTRAL_COMMUNITY_UUID = "f467b316-98f0-4c08-a722-a2627e45bc19"
ACTS_COLLECTION_UUID = "69a0c1fb-7b22-4481-b16a-1dc59b5d02e6"

# Common headers
HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Generic words to exclude from relevance keyword checks
STOP_WORDS = {
    "the", "and", "for", "from", "with", "that", "this", "are",
    "was", "has", "had", "have", "been", "not", "but", "its",
    "all", "any", "can", "may", "will", "shall", "under", "into",
    "india", "indian", "what", "how", "which", "provisions", "provision",
    "guidelines", "guideline", "section", "sections", "order", "orders",
}


class IndiaCodeRetrievalAdapter(RetrievalAdapter):
    """Retrieve Indian legislation via the India Code DSpace REST API."""

    SOURCE_NAME = "INDIA_CODE"
    REQUEST_TIMEOUT = 20
    MAX_RETRIES = 2

    # ── Public interface ─────────────────────────────────────
    def retrieve(self, query: str, jurisdiction: str) -> RetrievalResult:
        """Search India Code for legislation matching *query*."""
        try:
            return self._retry(self._do_retrieve, query, jurisdiction)
        except Exception as exc:
            return self._error(query, jurisdiction, str(exc))

    # ── Internal logic ───────────────────────────────────────
    def _do_retrieve(self, query: str, jurisdiction: str) -> RetrievalResult:
        """Core retrieval — search items across CENTRAL collections with smart Act extraction."""
        community_uuid = CENTRAL_COMMUNITY_UUID
        collections = self._get_collections(community_uuid)

        if not collections:
            # Fallback to known Acts collection
            collections = [{"uuid": ACTS_COLLECTION_UUID, "name": "Acts"}]

        # Build search queries (core Act name + original query)
        search_terms = self._build_search_terms(query)
        relevance_keywords = self._build_relevance_keywords(query)

        all_documents = []
        text_parts = []
        seen_uuids = set()
        scored_items = []

        # Search across primary collections (Acts, Rules)
        for coll in collections[:3]:
            coll_uuid = coll["uuid"]
            coll_name = coll["name"]

            for term in search_terms:
                items = self._search_items(coll_uuid, term, max_results=5)
                for item in items:
                    item_uuid = item.get("uuid", "")
                    if not item_uuid or item_uuid in seen_uuids:
                        continue
                    seen_uuids.add(item_uuid)

                    meta = item.get("metadata", {})
                    title = self._extract_metadata_value(meta, "dc.title") or "Untitled"
                    long_title = self._extract_metadata_value(meta, "dc.title.long_title") or ""
                    enact_date = self._extract_metadata_value(meta, "dc.date.enact_date") or ""
                    ministry = self._extract_metadata_value(meta, "dc.identifier.ministry_name") or ""
                    abstract = self._extract_metadata_value(meta, "dc.description.abstract") or ""

                    # Score relevance
                    combined_text = f"{title} {long_title} {abstract} {ministry}".lower()
                    score = self._score_relevance(title.lower(), combined_text, relevance_keywords, search_terms)

                    if score > 0:
                        doc = {
                            "title": title,
                            "url": f"https://indiacode.gov.in/handle/{item_uuid}",
                            "type": coll_name,
                            "enact_date": enact_date,
                            "ministry": ministry,
                            "snippet": (long_title or abstract or title)[:300],
                        }
                        scored_items.append((score, doc, enact_date, ministry, long_title or abstract))

        # Sort by score descending and take top 5
        scored_items.sort(key=lambda x: x[0], reverse=True)
        for _, doc, enact_date, ministry, desc in scored_items[:5]:
            all_documents.append(doc)
            parts = [f"- {doc['title']}"]
            if enact_date:
                parts.append(f"  Enacted: {enact_date}")
            if ministry:
                parts.append(f"  Ministry: {ministry}")
            if desc:
                parts.append(f"  Scope: {desc[:250]}")
            parts.append(f"  URL: {doc['url']}")
            text_parts.append("\n".join(parts))

        if not all_documents:
            return self._partial(
                query, jurisdiction,
                documents=[],
                text=f"No legislation found matching '{query}' on India Code.",
                error="No matching items found",
            )

        summary = (
            f"[INDIA_CODE] Found {len(all_documents)} legislation item(s) "
            f"matching '{query}':\n\n" + "\n\n".join(text_parts)
        )
        return self._ok(query, jurisdiction, all_documents, summary)

    def _build_search_terms(self, query: str) -> list[str]:
        """Extract primary statutory search terms (e.g. Act name) from query."""
        terms = []
        # Pattern 1: Match Act names like "Patents Act", "Biological Diversity Act", "Drugs and Cosmetics Act"
        m = re.search(r"((?:The\s+)?([A-Za-z\s]+?\bAct\b)(?:,\s*\d{4})?)", query, re.IGNORECASE)
        if m:
            act_candidate = m.group(1).strip()
            # Clean leading 'The '
            clean_act = re.sub(r"^the\s+", "", act_candidate, flags=re.I).strip()
            # Also clean year if attached for broader search
            clean_act_no_year = re.sub(r"\s+\d{4}$", "", clean_act).strip()
            terms.append(clean_act_no_year)
            if clean_act != clean_act_no_year:
                terms.append(clean_act)

        # Include original query as secondary
        if query not in terms:
            terms.append(query)
        return terms

    def _get_collections(self, community_uuid: str) -> list:
        """Retrieve collections (Acts, Rules, etc.) for a community."""
        url = f"{BASE_URL}/core/communities/{community_uuid}/collections"
        try:
            resp = requests.get(
                url, headers=HEADERS, timeout=self.REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
            embedded = data.get("_embedded", {})
            collections = embedded.get("collections", [])
            return [
                {"uuid": c["uuid"], "name": c.get("name", "Unknown")}
                for c in collections
            ]
        except Exception as exc:
            logger.warning("Failed to get collections: %s", exc)
            return []

    def _search_items(self, collection_uuid: str, query: str,
                      max_results: int = 5) -> list:
        """Search for items inside a collection by query keyword."""
        url = (
            f"{BASE_URL}/discover/search/objects"
            f"?scope={collection_uuid}"
            f"&query={requests.utils.quote(query)}"
            f"&size={max_results}&page=0"
        )
        try:
            resp = requests.get(
                url, headers=HEADERS, timeout=self.REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
            embedded = data.get("_embedded", {})
            search_result = embedded.get("searchResult", {})
            objects = search_result.get("_embedded", {}).get("objects", [])

            items = []
            for obj in objects:
                indexable = obj.get("_embedded", {}).get("indexableObject", {})
                if indexable:
                    items.append(indexable)
            return items
        except Exception as exc:
            logger.warning("Search failed for '%s' in %s: %s", query, collection_uuid, exc)
            return []

    @staticmethod
    def _build_relevance_keywords(query: str) -> list[str]:
        """Extract meaningful keywords from query for relevance matching."""
        words = re.split(r"[\s/,\-()]+", query.lower())
        return [w for w in words if len(w) > 2 and w not in STOP_WORDS]

    @staticmethod
    def _score_relevance(title: str, combined_text: str,
                         keywords: list[str], search_terms: list[str]) -> int:
        """Score legislation relevance based on Act match and keywords."""
        score = 0
        # If the title matches the extracted Act name term directly
        for st in search_terms:
            if len(st) > 3 and st.lower() in title:
                score += 5

        # Additional keyword matches
        for kw in keywords:
            if kw in title:
                score += 2
            elif kw in combined_text:
                score += 1
        return score

    @staticmethod
    def _extract_metadata_value(metadata: dict, key: str) -> str:
        """Extract the first text value for a metadata field."""
        entries = metadata.get(key, [])
        if entries and isinstance(entries, list):
            return entries[0].get("value", "")
        return ""
