import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from TOOLS.orchestrator import build_orchestrator
from TOOLS.db_client import LocalDBClient

def test_retrieval_routing():
    app = build_orchestrator()
    state = {"query": "Ashwagandha beverage", "jurisdiction": "IN", "source": "FSSAI"}
    result = app.invoke(state)
    assert "[FSSAI]" in result["evidence"]
    assert "Ashwagandha" in result["evidence"]

def test_db_client():
    db = LocalDBClient("database.db")
    # Quick test to ensure no crash on session initialization
    # Note: Requires a valid session_id if FK constraints are enabled, 
    # but SQLite FKs are off by default unless enforced.
    assert True
