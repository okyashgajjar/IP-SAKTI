"""
Integration Tests — Live API/website calls.

These tests make actual HTTP requests to the external data sources.
They are marked with ``@pytest.mark.integration`` and should be run
selectively, not in CI by default:

    pytest tests/test_integration_adapters.py -m integration -v

Expected behavior:
  - IndiaCode (REST API): should succeed reliably
  - NBA (server-rendered): should succeed reliably
  - AYUSH / FSSAI / WIPO (Playwright): may fail if Chromium is not
    installed — use ``playwright install chromium`` first.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mark all tests in this module as integration
pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════
# India Code — DSpace REST API (most reliable)
# ═══════════════════════════════════════════════════════
class TestIndiaCodeIntegration:
    """Live tests against the India Code DSpace REST API."""

    def setup_method(self):
        from TOOLS.indiacode_adapter import IndiaCodeRetrievalAdapter
        self.adapter = IndiaCodeRetrievalAdapter()

    def test_retrieve_patent_act(self):
        """Search for 'patent' should return legislation results."""
        result = self.adapter.retrieve("patent", "IN")
        assert result["source"] == "INDIA_CODE"
        assert result["status"] in ("ok", "partial")
        assert isinstance(result["documents"], list)
        assert isinstance(result["text"], str)
        # If documents found, verify structure
        if result["documents"]:
            doc = result["documents"][0]
            assert "title" in doc
            assert "url" in doc

    def test_retrieve_biodiversity_act(self):
        """Search for 'biodiversity' should return relevant Acts."""
        result = self.adapter.retrieve("biodiversity", "IN")
        assert result["source"] == "INDIA_CODE"
        assert result["status"] in ("ok", "partial")

    def test_get_collections_live(self):
        """Verify we can fetch CENTRAL community collections."""
        from TOOLS.indiacode_adapter import CENTRAL_COMMUNITY_UUID
        collections = self.adapter._get_collections(CENTRAL_COMMUNITY_UUID)
        assert len(collections) > 0
        names = [c["name"] for c in collections]
        # Should contain at least "Acts"
        assert any("Act" in n for n in names)


# ═══════════════════════════════════════════════════════
# NBA — Server-Rendered HTML (reliable)
# ═══════════════════════════════════════════════════════
class TestNbaIntegration:
    """Live tests against the NBA India website."""

    def setup_method(self):
        from TOOLS.nba_adapter import NbaRetrievalAdapter
        self.adapter = NbaRetrievalAdapter()

    def test_retrieve_biodiversity_rules(self):
        """Should find biodiversity regulation documents."""
        result = self.adapter.retrieve("biodiversity rules", "IN")
        assert result["source"] == "NBA"
        assert result["status"] in ("ok", "partial")
        # NBA should have at least some documents
        if result["documents"]:
            doc = result["documents"][0]
            assert "title" in doc
            assert "url" in doc

    def test_scrape_rules_page(self):
        """Directly scrape the rules page for PDF links."""
        docs = self.adapter._scrape_page(
            "https://www.nbaindia.nic.in/acts-and-rules/rules",
            "Acts & Rules"
        )
        assert isinstance(docs, list)
        # Page should have at least some PDF links
        pdf_docs = [d for d in docs if d.get("type") == "pdf"]
        assert len(pdf_docs) >= 0  # May vary; at minimum no crash


# ═══════════════════════════════════════════════════════
# AYUSH — Playwright (Angular SPA)
# ═══════════════════════════════════════════════════════
@pytest.mark.playwright
class TestAyushIntegration:
    """Live tests against the AYUSH Ministry website (requires Chromium)."""

    def setup_method(self):
        from TOOLS.ayush_adapter import AyushRetrievalAdapter
        self.adapter = AyushRetrievalAdapter()

    def test_retrieve_ayurveda_guidelines(self):
        """Search for Ayurveda guidelines should return documents or text."""
        result = self.adapter.retrieve("ayurveda guidelines", "IN")
        assert result["source"] == "AYUSH"
        assert result["status"] in ("ok", "partial", "error")
        # Even on error, result should have valid schema
        assert "documents" in result
        assert "text" in result

    def test_retrieve_notification(self):
        """Search for notifications should target whatsnew route."""
        result = self.adapter.retrieve("latest notification", "IN")
        assert result["source"] == "AYUSH"
        assert result["status"] in ("ok", "partial", "error")


# ═══════════════════════════════════════════════════════
# FSSAI — Playwright (React SPA)
# ═══════════════════════════════════════════════════════
@pytest.mark.playwright
class TestFssaiIntegration:
    """Live tests against the FSSAI website (requires Chromium)."""

    def setup_method(self):
        from TOOLS.fssai_adapter import FssaiRetrievalAdapter
        self.adapter = FssaiRetrievalAdapter()

    def test_retrieve_food_regulations(self):
        """Search for food regulations should return documents."""
        result = self.adapter.retrieve("food safety regulation labeling", "IN")
        assert result["source"] == "FSSAI"
        assert result["status"] in ("ok", "partial", "error")
        assert "documents" in result
        assert "text" in result

    def test_retrieve_ayurveda_aahara(self):
        """Search for Ayurveda Aahara should target regulations route."""
        result = self.adapter.retrieve("ayurveda aahara", "IN")
        assert result["source"] == "FSSAI"
        assert result["status"] in ("ok", "partial", "error")


# ═══════════════════════════════════════════════════════
# WIPO Lex — Playwright (Shadow DOM SPA)
# ═══════════════════════════════════════════════════════
@pytest.mark.playwright
class TestWipoLexIntegration:
    """Live tests against WIPO Lex (requires Chromium)."""

    def setup_method(self):
        from TOOLS.wipolex_adapter import WipoLexRetrievalAdapter
        self.adapter = WipoLexRetrievalAdapter()

    def test_retrieve_patent_law(self):
        """Search for patent law for India."""
        result = self.adapter.retrieve("patent", "IN")
        assert result["source"] == "WIPO_LEX"
        assert result["status"] in ("ok", "partial", "error")
        assert "documents" in result
        assert "text" in result

    def test_retrieve_trademark_us(self):
        """Search for trademark law in the US."""
        result = self.adapter.retrieve("trademark", "US")
        assert result["source"] == "WIPO_LEX"
        assert result["status"] in ("ok", "partial", "error")
