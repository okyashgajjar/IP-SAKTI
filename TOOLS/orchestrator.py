from typing import TypedDict, Annotated, Sequence
import operator
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
    evidence: str

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
        evidence = f"Source {source} not supported."
        
    return {"evidence": evidence}

def build_orchestrator():
    workflow = StateGraph(AgentState)
    workflow.add_node("retrieve", retrieve_node)
    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", END)
    return workflow.compile()
