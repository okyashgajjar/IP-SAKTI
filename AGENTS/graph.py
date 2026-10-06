"""
LangGraph Orchestrator - Graph Builder.
Compiles the full multi-agent pipeline from nodes.

Architecture flow:
  input_language → query_understanding → research_planner (plan + queries)
  → evidence_retrieval → evidence_reasoner → citation_validator
  → confidence_assessor → answer_synthesis → END
"""
from langgraph.graph import StateGraph, END

from AGENTS.state import OrchestratorState
from AGENTS.nodes import (
    input_language_node,
    query_understanding_node,
    research_planner_node,
    evidence_retrieval_node,
    evidence_reasoner_node,
    citation_validator_node,
    confidence_assessor_node,
    answer_synthesis_node,
)


def build_graph():
    """Build and compile the full LangGraph orchestrator."""
    workflow = StateGraph(OrchestratorState)

    # ── Register Nodes ──
    workflow.add_node("input_language", input_language_node)
    workflow.add_node("query_understanding", query_understanding_node)
    workflow.add_node("research_planner", research_planner_node)
    workflow.add_node("evidence_retrieval", evidence_retrieval_node)
    workflow.add_node("evidence_reasoner", evidence_reasoner_node)
    workflow.add_node("citation_validator", citation_validator_node)
    workflow.add_node("confidence_assessor", confidence_assessor_node)
    workflow.add_node("answer_synthesis", answer_synthesis_node)

    # ── Conditional Routing ──
    def route_after_confidence(state: OrchestratorState) -> str:
        """Decide the next step based on confidence and citations."""
        # 1. High Risk / Escalation needed -> skip to END (or a human queue)
        if state.get("needs_escalation"):
            return "end"
            
        # 2. Invalid citations -> Loop back to Planner to fetch more evidence
        if not state.get("citations_valid") and state.get("retry_count", 0) < 2:
            print("  🔄  LOOP TRIGGERED: Insufficient evidence/citations. Re-planning...")
            return "research_planner"
            
        # 3. Success / Default -> Synthesis
        return "answer_synthesis"

    # ── Wire Edges ──
    workflow.set_entry_point("input_language")
    workflow.add_edge("input_language", "query_understanding")
    workflow.add_edge("query_understanding", "research_planner")
    workflow.add_edge("research_planner", "evidence_retrieval")
    workflow.add_edge("evidence_retrieval", "evidence_reasoner")
    workflow.add_edge("evidence_reasoner", "citation_validator")
    workflow.add_edge("citation_validator", "confidence_assessor")
    
    workflow.add_conditional_edges(
        "confidence_assessor",
        route_after_confidence,
        {
            "research_planner": "research_planner",
            "answer_synthesis": "answer_synthesis",
            "end": END
        }
    )
    
    workflow.add_edge("answer_synthesis", END)

    return workflow.compile()


# Singleton compiled graph
orchestrator = build_graph()
