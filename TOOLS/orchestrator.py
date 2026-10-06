"""
Tool Orchestrator — LangGraph-based retrieval routing.

Routes queries to the appropriate data-source adapter and returns
standardized ``RetrievalResult`` evidence dicts.
"""
from typing import TypedDict
from langgraph.graph import StateGraph, END
from .ayush_adapter import AyushRetrievalAdapter
from .fssai_adapter import FssaiRetrievalAdapter
from .indiacode_adapter import IndiaCodeRetrievalAdapter
from .nba_adapter import NbaRetrievalAdapter
from .wipolex_adapter import WipoLexRetrievalAdapter

class AgentState(TypedDict):
    query: str
    jurisdiction: str
    source: str
    evidence: dict  # Changed from str → dict (RetrievalResult)

def retrieve_node(state: AgentState):
    source = state.get("source")
    query = state.get("query")
    jurisdiction = state.get("jurisdiction")
    
    adapters = {
        "AYUSH": AyushRetrievalAdapter(),
        "FSSAI": FssaiRetrievalAdapter(),
        "INDIA_CODE": IndiaCodeRetrievalAdapter(),
        "NBA": NbaRetrievalAdapter(),
        "WIPO_LEX": WipoLexRetrievalAdapter()
    }
    
    adapter = adapters.get(source)
    if adapter:
        evidence = adapter.retrieve(query, jurisdiction)
    else:
        evidence = {
            "source": source or "UNKNOWN",
            "query": query,
            "jurisdiction": jurisdiction,
            "status": "error",
            "documents": [],
            "text": f"Source '{source}' not supported.",
            "error": f"Source '{source}' not supported.",
        }
        
    return {"evidence": evidence}

def build_orchestrator():
    workflow = StateGraph(AgentState)
    workflow.add_node("retrieve", retrieve_node)
    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", END)
    return workflow.compile()
