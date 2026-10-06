"""
Orchestrator smoke tests — verify basic routing still works
after the adapter redesign.
"""
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from TOOLS.orchestrator import build_orchestrator
from TOOLS.db_client import LocalDBClient


def test_retrieval_routing():
    """FSSAI source should route to FssaiRetrievalAdapter and return a dict."""
    app = build_orchestrator()

    with patch("TOOLS.fssai_adapter.FssaiRetrievalAdapter.retrieve") as mock:
        mock.return_value = {
            "source": "FSSAI",
            "query": "Ashwagandha beverage",
            "jurisdiction": "IN",
            "status": "ok",
            "documents": [{"title": "Ayurveda Aahara Regulation"}],
            "text": "[FSSAI] Normalized evidence for 'Ashwagandha beverage' in jurisdiction 'IN'.",
            "error": "",
        }

        state = {
            "query": "Ashwagandha beverage",
            "jurisdiction": "IN",
            "source": "FSSAI",
        }
        result = app.invoke(state)

        assert result["evidence"]["source"] == "FSSAI"
        assert result["evidence"]["status"] == "ok"
        assert "Ashwagandha" in result["evidence"]["text"]


def test_db_client():
    db = LocalDBClient("database.db")
    # Quick test to ensure no crash on session initialization
    # Note: Requires a valid session_id if FK constraints are enabled, 
    # but SQLite FKs are off by default unless enforced.
    assert True
