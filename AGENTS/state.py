"""
State definitions for the LangGraph Orchestrator.
Each TypedDict maps 1:1 to a state node in the architecture diagram.
"""
from typing import TypedDict, Optional


class OrchestratorState(TypedDict):
    """Full state flowing through the LangGraph pipeline."""

    # ── Input & Language State ──
    user_query: str
    detected_language: str

    # ── Product + Intent + Jurisdiction State ──
    intent: str                # classify | ip_type | abs | regulatory
    jurisdiction: str          # IN | US | WIPO | etc.
    product_classification: str  # classical | proprietary | new_drug | etc.

    # ── Task Queue State ──
    sources_to_query: list[str]  # ["AYUSH", "FSSAI", "INDIA_CODE", ...]

    # ── Evidence Store ──
    evidence: list[dict]  # [{source, text, metadata}, ...]

    # ── Findings + Conflicts State ──
    findings: str

    # ── Citation + Validation State ──
    citations_valid: bool

    # ── Confidence Risk State ──
    confidence: str    # high | medium | low
    risk_level: str    # low | medium | high

    # ── Loop Management ──
    retry_count: int

    # ── Final Answer State ──
    final_answer: str
    needs_escalation: bool

    # ── Conversation Memory ──
    chat_history: list[dict]  # [{role, content}, ...]
    session_id: str
