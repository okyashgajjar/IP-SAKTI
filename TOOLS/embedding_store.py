"""
Embedding Store — Semantic Vector Storage using Google Gemini Embeddings.

Stores 3 types of content as embeddings:
  1. Chat history (session-wise)
  2. Evidence documents (session-wise, from adapter retrievals)
  3. Supports similarity search to reuse past evidence

Uses SQLite for persistence + numpy for cosine similarity.
"""
import os
import json
import uuid
import sqlite3
import numpy as np
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class EmbeddingStore:
    """Vector store backed by SQLite + Google Gemini Embeddings."""

    def __init__(self, db_path: str = "embeddings.db"):
        self.db_path = db_path
        self._init_db()
        self._init_client()

    def _init_client(self):
        """Initialize the Google GenAI client for embeddings."""
        from google import genai
        api_key = os.getenv("GOOGLE_API_KEY", "")
        if not api_key:
            print("  ⚠️  GOOGLE_API_KEY not set — embeddings will be disabled.")
            self.client = None
            return
        self.client = genai.Client(api_key=api_key)

    def _init_db(self):
        """Create embedding tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    source TEXT DEFAULT '',
                    content TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_emb_session
                ON embeddings(session_id, content_type)
            """)
            conn.commit()

    # ── Embedding Generation ──

    def _embed(self, text: str) -> Optional[list[float]]:
        """Generate embedding vector using Gemini Embedding 2."""
        if not self.client:
            return None
        try:
            # Truncate to ~8000 chars to stay within token limits
            text = text[:8000]
            result = self.client.models.embed_content(
                model="gemini-embedding-2",
                contents=text,
            )
            return result.embeddings[0].values
        except Exception as e:
            print(f"  ⚠️  Embedding error: {e}")
            return None

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        a_arr = np.array(a, dtype=np.float32)
        b_arr = np.array(b, dtype=np.float32)
        dot = np.dot(a_arr, b_arr)
        norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
        if norm == 0:
            return 0.0
        return float(dot / norm)

    # ── Storage Operations ──

    def store(
        self,
        session_id: str,
        content_type: str,
        content: str,
        source: str = "",
    ) -> Optional[str]:
        """
        Embed and store content.

        Args:
            session_id: Chat session ID
            content_type: 'history' | 'evidence'
            content: The text to embed
            source: Source name (e.g. 'INDIA_CODE', 'user', 'assistant')

        Returns:
            The embedding ID, or None if embedding failed.
        """
        embedding = self._embed(content)
        if embedding is None:
            return None

        emb_id = str(uuid.uuid4())
        emb_blob = np.array(embedding, dtype=np.float32).tobytes()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO embeddings
                   (id, session_id, content_type, source, content, embedding)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (emb_id, session_id, content_type, source, content, emb_blob),
            )
            conn.commit()
        return emb_id

    def store_chat_message(self, session_id: str, role: str, content: str) -> Optional[str]:
        """Store a chat message embedding (history type)."""
        return self.store(
            session_id=session_id,
            content_type="history",
            content=f"{role}: {content}",
            source=role,
        )

    def store_evidence(
        self, session_id: str, source: str, text: str
    ) -> Optional[str]:
        """Store retrieved evidence embedding."""
        return self.store(
            session_id=session_id,
            content_type="evidence",
            content=text,
            source=source,
        )

    # ── Retrieval Operations ──

    def search(
        self,
        query: str,
        content_type: Optional[str] = None,
        session_id: Optional[str] = None,
        top_k: int = 5,
        threshold: float = 0.5,
    ) -> list[dict]:
        """
        Semantic search across stored embeddings.

        Args:
            query: Search query text
            content_type: Filter by 'history' or 'evidence' (None = all)
            session_id: Filter by session (None = all sessions)
            top_k: Max results to return
            threshold: Min cosine similarity score

        Returns:
            List of {id, session_id, content_type, source, content, score}
        """
        query_emb = self._embed(query)
        if query_emb is None:
            return []

        # Build SQL filter
        where_clauses = []
        params = []
        if content_type:
            where_clauses.append("content_type = ?")
            params.append(content_type)
        if session_id:
            where_clauses.append("session_id = ?")
            params.append(session_id)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT id, session_id, content_type, source, content, embedding FROM embeddings {where_sql}",
                params,
            ).fetchall()

        results = []
        for row in rows:
            stored_emb = np.frombuffer(row["embedding"], dtype=np.float32).tolist()
            score = self._cosine_similarity(query_emb, stored_emb)
            if score >= threshold:
                results.append({
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "content_type": row["content_type"],
                    "source": row["source"],
                    "content": row["content"],
                    "score": round(score, 4),
                })

        # Sort by score descending, return top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def search_history(self, query: str, session_id: Optional[str] = None, top_k: int = 5) -> list[dict]:
        """Search past chat history embeddings."""
        return self.search(query, content_type="history", session_id=session_id, top_k=top_k)

    def search_evidence(self, query: str, session_id: Optional[str] = None, top_k: int = 5) -> list[dict]:
        """Search past evidence embeddings across sessions."""
        return self.search(query, content_type="evidence", session_id=session_id, top_k=top_k)

    def get_stats(self) -> dict:
        """Get counts of stored embeddings."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT content_type, COUNT(*) as cnt FROM embeddings GROUP BY content_type"
            ).fetchall()
        return {row["content_type"]: row["cnt"] for row in rows}
