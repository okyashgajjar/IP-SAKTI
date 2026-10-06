"""
Unit Tests — Adapter logic in isolation (no network calls).

Tests validate:
  1. Base adapter helper methods (_ok, _error, _partial, _retry)
  2. Each adapter's query → route mapping / keyword logic
  3. IndiaCode metadata extraction
  4. NBA HTML parsing
  5. Return format compliance (RetrievalResult schema)
"""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from TOOLS.base_adapter import RetrievalAdapter, RetrievalResult


# ═══════════════════════════════════════════════════════
# 1. Base Adapter Helper Tests
# ═══════════════════════════════════════════════════════
class ConcreteAdapter(RetrievalAdapter):
    """Minimal concrete adapter for testing base class methods."""
    SOURCE_NAME = "TEST"

    def retrieve(self, query, jurisdiction):
        return self._ok(query, jurisdiction, [], "test text")


class TestBaseAdapterHelpers:
    def setup_method(self):
        self.adapter = ConcreteAdapter()

    def test_ok_result(self):
        result = self.adapter._ok("query", "IN", [{"title": "doc"}], "text")
        assert result["source"] == "TEST"
        assert result["status"] == "ok"
        assert result["error"] == ""
        assert len(result["documents"]) == 1
        assert result["text"] == "text"
        assert result["query"] == "query"
        assert result["jurisdiction"] == "IN"

    def test_error_result(self):
        result = self.adapter._error("q", "IN", "timeout")
        assert result["status"] == "error"
        assert result["error"] == "timeout"
        assert result["documents"] == []
        assert "unavailable" in result["text"].lower()

    def test_partial_result(self):
        result = self.adapter._partial("q", "IN", [{"title": "d"}], "some text", "partial err")
        assert result["status"] == "partial"
        assert result["error"] == "partial err"
        assert len(result["documents"]) == 1

    def test_retry_succeeds_on_second_attempt(self):
        call_count = {"n": 0}

        def flaky_func():
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise ValueError("transient error")
            return "success"

        self.adapter.RETRY_DELAY = 0.01  # Fast for tests
        result = self.adapter._retry(flaky_func)
        assert result == "success"
        assert call_count["n"] == 2

    def test_retry_exhausted_raises(self):
        def always_fail():
            raise RuntimeError("permanent failure")

        self.adapter.RETRY_DELAY = 0.01
        self.adapter.MAX_RETRIES = 2
        with pytest.raises(RuntimeError, match="permanent failure"):
            self.adapter._retry(always_fail)

    def test_result_schema_keys(self):
        """Verify all required RetrievalResult keys are present."""
        result = self.adapter.retrieve("test", "IN")
        required_keys = {"source", "query", "jurisdiction", "status",
                         "documents", "text", "error"}
        assert required_keys.issubset(result.keys())


# ═══════════════════════════════════════════════════════
# 2. IndiaCode Adapter — Unit Tests
# ═══════════════════════════════════════════════════════
class TestIndiaCodeAdapter:
    def setup_method(self):
        from TOOLS.indiacode_adapter import IndiaCodeRetrievalAdapter
        self.adapter = IndiaCodeRetrievalAdapter()

    def test_extract_metadata_value(self):
        metadata = {
            "dc.title": [{"value": "Test Act 2021"}],
            "dc.date.enact_date": [{"value": "2021-01-01"}],
        }
        assert self.adapter._extract_metadata_value(metadata, "dc.title") == "Test Act 2021"
        assert self.adapter._extract_metadata_value(metadata, "dc.date.enact_date") == "2021-01-01"
        assert self.adapter._extract_metadata_value(metadata, "dc.nonexistent") == ""

    def test_extract_metadata_empty_list(self):
        assert self.adapter._extract_metadata_value({"dc.title": []}, "dc.title") == ""

    def test_extract_metadata_non_list(self):
        assert self.adapter._extract_metadata_value({"dc.title": "string"}, "dc.title") == ""

    @patch("TOOLS.indiacode_adapter.requests.get")
    def test_get_collections_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "_embedded": {
                "collections": [
                    {"uuid": "uuid-1", "name": "Acts"},
                    {"uuid": "uuid-2", "name": "Rule"},
                ]
            }
        }
        mock_get.return_value = mock_resp

        collections = self.adapter._get_collections("community-uuid")
        assert len(collections) == 2
        assert collections[0]["name"] == "Acts"

    @patch("TOOLS.indiacode_adapter.requests.get")
    def test_get_collections_failure(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        collections = self.adapter._get_collections("community-uuid")
        assert collections == []

    @patch("TOOLS.indiacode_adapter.requests.get")
    def test_search_items_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "_embedded": {
                "searchResult": {
                    "_embedded": {
                        "objects": [
                            {
                                "_embedded": {
                                    "indexableObject": {
                                        "uuid": "item-uuid-1",
                                        "metadata": {
                                            "dc.title": [{"value": "Patent Act"}]
                                        }
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        }
        mock_get.return_value = mock_resp

        items = self.adapter._search_items("coll-uuid", "patent")
        assert len(items) == 1
        assert items[0]["metadata"]["dc.title"][0]["value"] == "Patent Act"

    @patch("TOOLS.indiacode_adapter.requests.get")
    def test_retrieve_no_collections(self, mock_get):
        """When collections API fails, adapter returns error gracefully."""
        mock_get.side_effect = Exception("API down")
        self.adapter.RETRY_DELAY = 0.01

        result = self.adapter.retrieve("patent act", "IN")
        assert result["status"] == "error"
        assert result["source"] == "INDIA_CODE"


# ═══════════════════════════════════════════════════════
# 3. NBA Adapter — Unit Tests
# ═══════════════════════════════════════════════════════
class TestNbaAdapter:
    def setup_method(self):
        from TOOLS.nba_adapter import NbaRetrievalAdapter
        self.adapter = NbaRetrievalAdapter()

    def test_absolute_url_relative(self):
        result = self.adapter._absolute_url("/sites/default/files/test.pdf")
        assert result == "https://www.nbaindia.nic.in/sites/default/files/test.pdf"

    def test_absolute_url_already_absolute(self):
        result = self.adapter._absolute_url("https://example.com/file.pdf")
        assert result == "https://example.com/file.pdf"

    def test_title_from_href(self):
        assert "BD Rules" in self.adapter._title_from_href(
            "/sites/default/files/BD_Rules.pdf"
        )

    def test_title_from_href_empty(self):
        assert self.adapter._title_from_href("") == "Document"

    @patch("TOOLS.nba_adapter.requests.get")
    def test_scrape_page_extracts_pdf_links(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """
        <html><body>
            <a class="download-link" href="/sites/default/files/BD_Rules.pdf">
                Biological Diversity Rules
            </a>
            <a href="/sites/default/files/Guidelines.pdf">Guidelines</a>
        </body></html>
        """
        mock_get.return_value = mock_resp

        docs = self.adapter._scrape_page(
            "https://www.nbaindia.nic.in/acts-and-rules/rules",
            "Acts & Rules"
        )
        assert len(docs) >= 1
        assert any("Biological Diversity" in d["title"] or "BD" in d["title"]
                    for d in docs)

    @patch("TOOLS.nba_adapter.requests.get")
    def test_retrieve_all_pages_fail(self, mock_get):
        """When all page requests fail, adapter returns error."""
        mock_get.side_effect = Exception("Connection refused")
        self.adapter.RETRY_DELAY = 0.01

        result = self.adapter.retrieve("biodiversity", "IN")
        assert result["status"] == "error"
        assert result["source"] == "NBA"


# ═══════════════════════════════════════════════════════
# 4. AYUSH Adapter — Unit Tests (route selection only)
# ═══════════════════════════════════════════════════════
class TestAyushAdapterRouting:
    def setup_method(self):
        from TOOLS.ayush_adapter import AyushRetrievalAdapter
        self.adapter = AyushRetrievalAdapter()

    def test_select_routes_ayurveda(self):
        routes = self.adapter._select_routes("ayurveda regulations guidelines")
        assert "ayurveda" in routes or "qualitystandard" in routes

    def test_select_routes_schemes(self):
        routes = self.adapter._select_routes("government scheme for ayush")
        assert "schemes" in routes

    def test_select_routes_notification(self):
        routes = self.adapter._select_routes("latest notification circular")
        assert "whatsnew" in routes

    def test_select_routes_default(self):
        routes = self.adapter._select_routes("something random")
        assert len(routes) >= 1  # Should default to whatsnew + ayurveda

    def test_select_routes_capped_at_3(self):
        routes = self.adapter._select_routes(
            "ayurveda notification scheme tender quality"
        )
        assert len(routes) <= 3

    def test_title_from_url(self):
        assert "Guidelines" in self.adapter._title_from_url(
            "https://ayush.gov.in/docs/Guidelines_2024.pdf"
        ) or "guidelines" in self.adapter._title_from_url(
            "https://ayush.gov.in/docs/Guidelines_2024.pdf"
        ).lower()


# ═══════════════════════════════════════════════════════
# 5. FSSAI Adapter — Unit Tests (route selection only)
# ═══════════════════════════════════════════════════════
class TestFssaiAdapterRouting:
    def setup_method(self):
        from TOOLS.fssai_adapter import FssaiRetrievalAdapter
        self.adapter = FssaiRetrievalAdapter()

    def test_select_routes_regulation(self):
        routes = self.adapter._select_routes("food regulation labeling")
        assert "regulations" in routes

    def test_select_routes_aahara(self):
        routes = self.adapter._select_routes("ayurveda aahara")
        assert "regulations" in routes or "notifications" in routes

    def test_select_routes_act(self):
        routes = self.adapter._select_routes("food safety act")
        assert "act" in routes

    def test_select_routes_default(self):
        routes = self.adapter._select_routes("random query")
        assert len(routes) >= 1

    def test_title_from_url(self):
        title = self.adapter._title_from_url(
            "https://fssai.gov.in/docs/Regulation_Labeling.pdf"
        )
        assert "Regulation" in title or "regulation" in title.lower()


# ═══════════════════════════════════════════════════════
# 6. WIPO Lex Adapter — Unit Tests
# ═══════════════════════════════════════════════════════
class TestWipoLexAdapterRouting:
    def setup_method(self):
        from TOOLS.wipolex_adapter import WipoLexRetrievalAdapter
        self.adapter = WipoLexRetrievalAdapter()

    def test_jurisdiction_to_country_india(self):
        assert self.adapter._jurisdiction_to_country("IN") == "IN"

    def test_jurisdiction_to_country_us(self):
        assert self.adapter._jurisdiction_to_country("US") == "US"

    def test_jurisdiction_to_country_uk(self):
        assert self.adapter._jurisdiction_to_country("UK") == "GB"

    def test_jurisdiction_to_country_unknown(self):
        result = self.adapter._jurisdiction_to_country("XYZ")
        assert len(result) == 2  # Should return first 2 chars
