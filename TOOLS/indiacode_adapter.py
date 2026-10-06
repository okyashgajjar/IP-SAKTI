"""
India Code Retrieval Adapter — DSpace REST API.

Retrieves legislation from https://indiacode.gov.in/ using its public
DSpace 7/9 REST API. No headless browser needed — pure JSON over HTTP.

API traversal:
  Communities (CENTRAL / State) → Collections (Acts, Rules, …)
  → Items (specific legislation) → metadata + PDF links
"""
import logging
import requests

from .base_adapter import RetrievalAdapter, RetrievalResult

logger = logging.getLogger(__name__)

BASE_URL = "https://indiacode.gov.in/server/api"

# Pre-verified UUIDs from DATA_SOURCES testing
CENTRAL_COMMUNITY_UUID = "f467b316-98f0-4c08-a722-a2627e45bc19"

# Mapping of collection names to expected types
COLLECTION_TYPES = ["Acts", "Rule", "Regulation", "Notification", "Order", "Ordinance"]

# Common headers
HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


class IndiaCodeRetrievalAdapter(RetrievalAdapter):
    """Retrieve Indian legislation via the India Code DSpace REST API."""

    SOURCE_NAME = "INDIA_CODE"
    REQUEST_TIMEOUT = 20

    # ── Public interface ─────────────────────────────────────
    def retrieve(self, query: str, jurisdiction: str) -> RetrievalResult:
        """Search India Code for legislation matching *query*."""
        try:
            return self._retry(self._do_retrieve, query, jurisdiction)
        except Exception as exc:
            return self._error(query, jurisdiction, str(exc))

    # ── Internal logic ───────────────────────────────────────
    def _do_retrieve(self, query: str, jurisdiction: str) -> RetrievalResult:
        """Core retrieval — search items across CENTRAL collections."""
        # Step 1: Get collections for CENTRAL community
        community_uuid = CENTRAL_COMMUNITY_UUID
        collections = self._get_collections(community_uuid)

        if not collections:
            return self._error(
                query, jurisdiction,
                "Could not retrieve collections from India Code API."
            )

        # Step 2: Search across relevant collections
        all_documents = []
        all_text_parts = []

        for coll in collections[:4]:  # Limit to first 4 collections to stay fast
            coll_uuid = coll["uuid"]
            coll_name = coll["name"]
            items = self._search_items(coll_uuid, query, max_results=5)

            for item in items:
                title = self._extract_metadata_value(
                    item.get("metadata", {}), "dc.title"
                )
                enact_date = self._extract_metadata_value(
                    item.get("metadata", {}), "dc.date.enact_date"
                )
                ministry = self._extract_metadata_value(
                    item.get("metadata", {}), "dc.identifier.ministry_name"
                )
                abstract = self._extract_metadata_value(
                    item.get("metadata", {}), "dc.description.abstract"
                )
                item_uuid = item.get("uuid", "")

                doc = {
                    "title": title or "Untitled",
                    "url": f"https://indiacode.gov.in/handle/{item_uuid}",
                    "type": coll_name,
                    "enact_date": enact_date,
                    "ministry": ministry,
                    "snippet": (abstract or "")[:300],
                }
                all_documents.append(doc)

                # Build summary text
                parts = [f"- {title}"]
                if enact_date:
                    parts.append(f"  Enacted: {enact_date}")
                if ministry:
                    parts.append(f"  Ministry: {ministry}")
                if abstract:
                    parts.append(f"  Summary: {abstract[:200]}")
                all_text_parts.append("\n".join(parts))

        if not all_documents:
            return self._partial(
                query, jurisdiction,
                documents=[],
                text=f"No legislation found matching '{query}' on India Code.",
                error="No matching items found",
            )

        summary = (
            f"[INDIA_CODE] Found {len(all_documents)} legislation item(s) "
            f"matching '{query}':\n\n" + "\n\n".join(all_text_parts)
        )
        return self._ok(query, jurisdiction, all_documents, summary)

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

            # Navigate the DSpace embedded structure
            search_result = data.get("_embedded", {}).get("searchResult", {})
            objects = (
                search_result.get("_embedded", {}).get("objects", [])
            )

            items = []
            for obj in objects:
                indexable = (
                    obj.get("_embedded", {}).get("indexableObject", {})
                )
                if indexable:
                    items.append(indexable)
            return items

        except Exception as exc:
            logger.warning(
                "Failed to search items in collection %s: %s",
                collection_uuid, exc,
            )
            return []

    @staticmethod
    def _extract_metadata_value(metadata: dict, key: str) -> str:
        """Extract the first value for a DSpace metadata key."""
        values = metadata.get(key, [])
        if isinstance(values, list) and values:
            return values[0].get("value", "")
        return ""
