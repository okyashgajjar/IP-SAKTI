"""
FastAPI Application Server.
Stateless API exposing the LangGraph orchestrator over HTTP + SSE.
"""
import os
import sys
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from AGENTS.graph import orchestrator
from TOOLS.db_client import LocalDBClient

app = FastAPI(title="Ayurveda IP Advisor", version="1.0.0")

# Serve static frontend files
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "frontend")),
    name="static",
)

db = LocalDBClient(os.getenv("DB_PATH", "database.db"))


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

    # Save user message to DB
    db.save_chat_message(session_id, "user", user_query)

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

        # Save assistant response to DB
        db.save_chat_message(session_id, "assistant", final_answer)

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


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "Ayurveda IP Advisor"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", 8000)),
        reload=True,
    )
