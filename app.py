"""
FastAPI Application Server.
Stateless API exposing the LangGraph orchestrator over HTTP + SSE.
"""
import os
import sys
import uuid
import uvicorn

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from AGENTS.graph import orchestrator
from TOOLS.db_client import LocalDBClient
from TOOLS.embedding_store import EmbeddingStore

app = FastAPI(title="Ayurveda IP Advisor", version="1.0.0")

# Serve static frontend files
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "frontend")),
    name="static",
)

db = LocalDBClient(os.getenv("DB_PATH", "database.db"))
embed_store = EmbeddingStore(os.getenv("EMBEDDINGS_DB_PATH", "embeddings.db"))


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main chat UI."""
    index_path = os.path.join(
        os.path.dirname(__file__), "frontend", "index.html"
    )
    with open(index_path, "r") as f:
        return HTMLResponse(content=f.read())


@app.post("/api/chat")
async def chat_endpoint(request: Request):
    """Main chat endpoint. Runs the full LangGraph pipeline."""
    body = await request.json()
    user_query = body.get("query", "")
    session_id = body.get("session_id", str(uuid.uuid4()))
    chat_history = body.get("chat_history", [])

    if not user_query.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "Query cannot be empty."},
        )

    # Save user message to DB + embed for history layer
    db.save_chat_message(session_id, "user", user_query)
    embed_store.store_chat_message(session_id, "user", user_query)

    # Build initial state for LangGraph
    initial_state = {
        "user_query": user_query,
        "session_id": session_id,
        "chat_history": chat_history,
        # Defaults (will be overwritten by nodes)
        "detected_language": "en",
        "intent": "",
        "jurisdiction": "IN",
        "product_classification": "unknown",
        "sources_to_query": [],
        "research_plan": "",
        "research_queue": {},
        "evidence": [],
        "findings": "",
        "citations_valid": False,
        "confidence": "medium",
        "risk_level": "medium",
        "final_answer": "",
        "needs_escalation": False,
    }

    try:
        # Run the full orchestrator pipeline
        result = orchestrator.invoke(initial_state)

        final_answer = result.get("final_answer", "No answer generated.")

        # Save assistant response to DB + embed for history layer
        db.save_chat_message(session_id, "assistant", final_answer)
        embed_store.store_chat_message(session_id, "assistant", final_answer)

        return JSONResponse(content={
            "answer": final_answer,
            "session_id": session_id,
            "metadata": {
                "intent": result.get("intent"),
                "jurisdiction": result.get("jurisdiction"),
                "classification": result.get("product_classification"),
                "sources_queried": result.get("sources_to_query"),
                "confidence": result.get("confidence"),
                "risk_level": result.get("risk_level"),
                "needs_escalation": result.get("needs_escalation"),
                "language": result.get("detected_language"),
            },
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Pipeline error: {str(e)}"},
        )


@app.get("/api/sessions")
async def api_get_sessions():
    """Get all chat sessions."""
    return JSONResponse(content={"sessions": db.get_sessions()})


@app.get("/api/chat/{session_id}")
async def api_get_chat_history(session_id: str):
    """Get chat history for a session."""
    return JSONResponse(content={"history": db.get_chat_history(session_id)})


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "Ayurveda IP Advisor"}


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", 8000)),
        reload=True,
    )
