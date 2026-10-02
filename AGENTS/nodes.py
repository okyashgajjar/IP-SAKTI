"""
Node functions for each stage of the LangGraph pipeline.

Architecture mapping:
  1. input_language_node     → Input & Language State
  2. query_understanding     → Query Understanding (LLM Agent)
  3. research_planner        → Research Planner Agent
  4. evidence_retrieval      → Deterministic Tool Connectors
  5. evidence_reasoner       → Evidence Reasoner Agent (LLM)
  6. citation_validator      → Citation + Validation State
  7. confidence_assessor     → Confidence Risk State
  8. answer_synthesizer      → Answer Synthesis Agent (LLM)
"""
import json
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# ── Pipeline Logger ──
def log_node(step: int, name: str, detail: str = ""):
    """Print colored pipeline progress to terminal."""
    icons = {
        1: "🌐", 2: "🧠", 3: "📋", 4: "🔍",
        5: "⚖️", 6: "📎", 7: "🎯", 8: "✍️",
    }
    icon = icons.get(step, "▶")
    msg = f"  {icon}  Node {step}/8 │ {name}"
    if detail:
        msg += f" → {detail}"
    print(msg, flush=True)

from AGENTS.state import OrchestratorState
from AGENTS.llm_provider import get_llm
from TOOLS.ayush_adapter import AyushRetrievalAdapter
from TOOLS.fssai_adapter import FssaiRetrievalAdapter
from TOOLS.indiacode_adapter import IndiaCodeRetrievalAdapter
from TOOLS.nba_adapter import NbaRetrievalAdapter
from TOOLS.wipolex_adapter import WipoLexRetrievalAdapter


# ── Adapter Registry (SOLID: Open/Closed) ──
ADAPTER_REGISTRY = {
    "AYUSH": AyushRetrievalAdapter(),
    "FSSAI": FssaiRetrievalAdapter(),
    "INDIA_CODE": IndiaCodeRetrievalAdapter(),
    "NBA": NbaRetrievalAdapter(),
    "WIPO_LEX": WipoLexRetrievalAdapter(),
}


# ───────────────────────────────────────────────
# Node 1: Input & Language State
# ───────────────────────────────────────────────
def input_language_node(state: OrchestratorState) -> dict:
    """Detect language of the user query."""
    print("\n" + "═" * 60, flush=True)
    print("  🚀  PIPELINE START", flush=True)
    print("═" * 60, flush=True)
    query = state.get("user_query", "")
    retry = state.get("retry_count", 0)
    # Simple heuristic; production would use langdetect or Bhashini
    has_devanagari = any("\u0900" <= ch <= "\u097F" for ch in query)
    lang = "hi" if has_devanagari else "en"
    log_node(1, "Input & Language", f"detected '{lang}' (Retry: {retry})")
    return {"detected_language": lang, "retry_count": retry}


# ───────────────────────────────────────────────
# Node 2: Query Understanding (LLM Agent)
# ───────────────────────────────────────────────
def query_understanding_node(state: OrchestratorState) -> dict:
    """Classify intent, jurisdiction, and product type using LLM."""
    log_node(2, "Query Understanding", "calling LLM...")
    llm = get_llm()
    query = state.get("user_query", "")
    history = state.get("chat_history", [])

    history_text = ""
    if history:
        recent = history[-6:]  # last 3 turns
        history_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in recent
        )

    prompt = f"""You are a legal classification engine for Ayurveda IP and
drug regulation queries. Analyze the user query and return ONLY valid JSON.

Conversation context:
{history_text}

User query: "{query}"

Return JSON with exactly these keys:
{{
  "intent": "classify | ip_type | abs | regulatory",
  "jurisdiction": "IN | US | WIPO | EU",
  "product_classification": "classical | proprietary | new_drug | phytopharma | aahara | cosmetic | unknown",
  "sources_to_query": ["AYUSH", "FSSAI", "INDIA_CODE", "NBA", "WIPO_LEX"]
}}

Rules:
- intent: what the user wants to know
- jurisdiction: default "IN" unless query mentions international/US/EU/WIPO
- product_classification: classify the product type if mentioned
- sources_to_query: pick ONLY relevant sources (1-3 max, not all)
  * AYUSH → Ayurveda regulations, schemes, guidelines
  * FSSAI → food safety, Ayurveda Aahara, labeling
  * INDIA_CODE → Acts, sections, patent law, BD Act
  * NBA → ABS, biodiversity, biological resources
  * WIPO_LEX → international IP treaties, patents abroad
"""

    response = llm.invoke(prompt)
    content = response.content.strip()

    # Parse JSON from LLM response
    try:
        # Strip markdown code fences if present
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        parsed = json.loads(content.strip())
    except (json.JSONDecodeError, IndexError):
        parsed = {
            "intent": "regulatory",
            "jurisdiction": "IN",
            "product_classification": "unknown",
            "sources_to_query": ["INDIA_CODE", "AYUSH"],
        }

    result = {
        "intent": parsed.get("intent", "regulatory"),
        "jurisdiction": parsed.get("jurisdiction", "IN"),
        "product_classification": parsed.get(
            "product_classification", "unknown"
        ),
        "sources_to_query": parsed.get(
            "sources_to_query", ["INDIA_CODE"]
        ),
    }
    log_node(2, "Query Understanding",
             f"intent={result['intent']} | "
             f"jurisdiction={result['jurisdiction']} | "
             f"class={result['product_classification']}")
    return result


# ───────────────────────────────────────────────
# Node 3: Research Planner (pass-through)
# Sources already decided by query_understanding
# ───────────────────────────────────────────────
def research_planner_node(state: OrchestratorState) -> dict:
    """Validate and finalize the task queue of sources."""
    sources = state.get("sources_to_query", [])
    valid = [s for s in sources if s in ADAPTER_REGISTRY]
    if not valid:
        valid = ["INDIA_CODE"]
    log_node(3, "Research Planner", f"querying → {valid}")
    return {"sources_to_query": valid}


# ───────────────────────────────────────────────
# Node 4: Evidence Retrieval (Deterministic Tools)
# ───────────────────────────────────────────────
def evidence_retrieval_node(state: OrchestratorState) -> dict:
    """Call each adapter in the task queue and collect evidence."""
    log_node(4, "Evidence Retrieval", "calling adapters...")
    sources = state.get("sources_to_query", [])
    query = state.get("user_query", "")
    jurisdiction = state.get("jurisdiction", "IN")

    evidence_list = []
    for source_name in sources:
        adapter = ADAPTER_REGISTRY.get(source_name)
        if adapter:
            try:
                result = adapter.retrieve(query, jurisdiction)
                evidence_list.append({
                    "source": source_name,
                    "text": result,
                    "status": "ok",
                })
            except Exception as e:
                evidence_list.append({
                    "source": source_name,
                    "text": f"Retrieval failed: {str(e)}",
                    "status": "error",
                })

    ok = sum(1 for e in evidence_list if e['status'] == 'ok')
    log_node(4, "Evidence Retrieval",
             f"{ok}/{len(evidence_list)} sources returned OK")
    return {"evidence": evidence_list}


# ───────────────────────────────────────────────
# Node 5: Evidence Reasoner (LLM Agent)
# ───────────────────────────────────────────────
def evidence_reasoner_node(state: OrchestratorState) -> dict:
    """Analyze evidence, find patterns, flag conflicts."""
    log_node(5, "Evidence Reasoner", "analyzing findings...")
    llm = get_llm()
    evidence = state.get("evidence", [])
    query = state.get("user_query", "")
    classification = state.get("product_classification", "unknown")

    evidence_text = "\n\n".join(
        f"[{e['source']}]: {e['text']}" for e in evidence
    )

    prompt = f"""You are a legal evidence analyst for Ayurveda IP law.

User question: "{query}"
Product classification: {classification}

Evidence collected:
{evidence_text}

Analyze the evidence and produce findings. Include:
1. Key legal provisions that apply
2. Any conflicts between sources
3. Specific section/act citations where possible
4. What the user should know

Be precise and cite sources. If evidence is insufficient, say so clearly.
"""

    response = llm.invoke(prompt)
    log_node(5, "Evidence Reasoner", "findings ready")
    return {"findings": response.content}


# ───────────────────────────────────────────────
# Node 6: Citation Validator
# ───────────────────────────────────────────────
def citation_validator_node(state: OrchestratorState) -> dict:
    """Check if findings contain proper citations."""
    findings = state.get("findings", "")
    # Simple heuristic: check for section/act references
    citation_keywords = [
        "Section", "Act", "Rule", "Regulation",
        "Article", "Notification", "Schedule",
    ]
    has_citations = any(kw in findings for kw in citation_keywords)
    log_node(6, "Citation Validator",
             f"citations={'✅ found' if has_citations else '❌ missing'}")
    return {"citations_valid": has_citations}


# ───────────────────────────────────────────────
# Node 7: Confidence Assessor
# ───────────────────────────────────────────────
def confidence_assessor_node(state: OrchestratorState) -> dict:
    """Score confidence and risk based on evidence quality."""
    evidence = state.get("evidence", [])
    citations_valid = state.get("citations_valid", False)
    retry_count = state.get("retry_count", 0)

    ok_count = sum(1 for e in evidence if e.get("status") == "ok")
    total = len(evidence) if evidence else 1

    if ok_count == total and citations_valid:
        confidence = "high"
        risk = "low"
    elif ok_count > 0:
        confidence = "medium"
        risk = "medium"
    else:
        confidence = "low"
        risk = "high"

    needs_escalation = (confidence == "low" and risk == "high")
    log_node(7, "Confidence Assessor",
             f"confidence={confidence} | risk={risk} | "
             f"escalate={'YES' if needs_escalation else 'no'}")
             
    return {
        "confidence": confidence,
        "risk_level": risk,
        "needs_escalation": needs_escalation,
        "retry_count": retry_count + 1
    }


# ───────────────────────────────────────────────
# Node 8: Answer Synthesis (LLM Agent)
# ───────────────────────────────────────────────
def answer_synthesis_node(state: OrchestratorState) -> dict:
    """Generate the final cited answer for the user."""
    log_node(8, "Answer Synthesis", "generating final answer...")
    llm = get_llm()
    findings = state.get("findings", "")
    query = state.get("user_query", "")
    confidence = state.get("confidence", "medium")
    jurisdiction = state.get("jurisdiction", "IN")
    classification = state.get("product_classification", "unknown")
    needs_escalation = state.get("needs_escalation", False)
    history = state.get("chat_history", [])

    history_text = ""
    if history:
        recent = history[-6:]
        history_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in recent
        )

    if needs_escalation:
        return {
            "final_answer": (
                "⚠️ **Low Confidence — Escalation Required**\n\n"
                "The evidence available is insufficient to provide a "
                "reliable answer to your question. This query has been "
                "flagged for review by a Human IP Facilitator.\n\n"
                f"**Your question:** {query}\n\n"
                "A domain expert will review this and respond shortly."
            )
        }

    prompt = f"""You are an expert Ayurveda IP and regulatory advisor
chatbot. Provide a clear, helpful answer based ONLY on the findings below.

Conversation history:
{history_text}

User question: "{query}"
Jurisdiction: {jurisdiction}
Product classification: {classification}
Confidence level: {confidence}

Research findings:
{findings}

Rules:
1. ALWAYS cite the specific Act, Section, or Rule for every claim
2. Use the format: [Source: Act/Section] for citations
3. Clearly state the jurisdiction (India / International)
4. If you cannot fully answer, say what is missing
5. Add a disclaimer: "This is informational guidance, not legal advice"
6. Keep the answer structured with headers and bullet points
7. If confidence is medium, note which parts are uncertain
8. DO NOT output any internal thinking process or "Here's a thinking process". Output ONLY the final answer directly.

"""

    response = llm.invoke(prompt)
    answer = response.content
    
    import re
    # Strip <think> tags completely
    answer = re.sub(r'<think>.*?</think>', '', answer, flags=re.DOTALL)
    
    # Strip "Here's a thinking process" text block
    if "Here's a thinking process" in answer:
        # Split on the first occurrence of a clear boundary if possible, 
        # but safely we can just split and take the last part if there's a delimiter like a horizontal rule or double line break after the list.
        # Alternatively, find the first occurrence of "Jurisdiction:" or similar structural element.
        parts = answer.split("Here's a thinking process", 1)
        # Try to find where the actual answer starts (usually after some list items)
        actual_answer_start = re.search(r'\n\s*\n(?!- )(?!\d+\.\s)', parts[1])
        if actual_answer_start:
            answer = parts[1][actual_answer_start.end():].strip()
        else:
            answer = answer.replace(parts[1], "").strip() # fallback

    return {"final_answer": answer.strip()}
