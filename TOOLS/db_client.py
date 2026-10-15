import os
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional

class PostgresDBClient:
    """Unified PostgreSQL client for chat history + pgvector embeddings."""
    
    def __init__(self, db_url="postgresql://postgres:postgres@localhost:5432/ayurveda_ip"):
        self.db_url = db_url
        self.init_db()
        self._init_embed_client()

    def _init_embed_client(self):
        """Initialize the Google GenAI client for embeddings."""
        from google import genai
        api_key = os.getenv("GOOGLE_API_KEY", "")
        if not api_key:
            print("  ⚠️  GOOGLE_API_KEY not set — embeddings will be disabled.")
            self.client = None
            return
        self.client = genai.Client(api_key=api_key)

    def _get_connection(self):
        return psycopg2.connect(self.db_url)

    def init_db(self):
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Enable pgvector extension
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                
                # Sessions Table
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY,
                        title TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Chat Messages Table
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id TEXT PRIMARY KEY,
                        session_id TEXT REFERENCES sessions(id),
                        role TEXT,
                        content TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Embeddings Table
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS embeddings (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        content_type TEXT NOT NULL,
                        source TEXT DEFAULT '',
                        content TEXT NOT NULL,
                        embedding vector(3072) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Index for filtering
                cur.execute('''
                    CREATE INDEX IF NOT EXISTS idx_emb_session
                    ON embeddings(session_id, content_type)
                ''')
            conn.commit()

    def execute_query(self, query, params=(), fetch=True):
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                if fetch:
                    return cur.fetchall()
            conn.commit()

    # ── Chat Operations ──
    
    def create_session_if_not_exists(self, session_id, title="New Chat"):
        res = self.execute_query("SELECT id FROM sessions WHERE id = %s", (session_id,))
        if not res:
            self.execute_query("INSERT INTO sessions (id, title) VALUES (%s, %s)", (session_id, title), fetch=False)

    def save_chat_message(self, session_id, role, content):
        self.create_session_if_not_exists(session_id)
        if role == 'user':
            res = self.execute_query("SELECT count(*) as cnt FROM chat_messages WHERE session_id = %s", (session_id,))
            if res and res[0]['cnt'] == 0:
                title = content[:30] + '...' if len(content) > 30 else content
                self.execute_query("UPDATE sessions SET title = %s WHERE id = %s", (title, session_id), fetch=False)

        msg_id = str(uuid.uuid4())
        self.execute_query(
            "INSERT INTO chat_messages (id, session_id, role, content) VALUES (%s, %s, %s, %s)",
            (msg_id, session_id, role, content), fetch=False
        )

    def get_sessions(self):
        # Convert datetime to string so FastAPI JSONResponse can serialize it easily
        res = self.execute_query("SELECT id, title, created_at FROM sessions ORDER BY created_at DESC")
        return [{"id": r["id"], "title": r["title"], "created_at": r["created_at"].isoformat()} for r in res]

    def get_chat_history(self, session_id):
        return self.execute_query("SELECT role, content FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC", (session_id,))

    # ── Embedding Operations ──
    
    def _embed(self, text: str) -> Optional[list[float]]:
        if not self.client:
            return None
        try:
            text = text[:8000]
            result = self.client.models.embed_content(
                model="gemini-embedding-2",
                contents=text,
            )
            return result.embeddings[0].values
        except Exception as e:
            print(f"  ⚠️  Embedding error: {e}")
            return None

    def store_embedding(self, session_id: str, content_type: str, content: str, source: str = "") -> Optional[str]:
        embedding = self._embed(content)
        if embedding is None:
            return None

        emb_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                vec_str = f"[{','.join(map(str, embedding))}]"
                cur.execute(
                    """INSERT INTO embeddings
                       (id, session_id, content_type, source, content, embedding)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (emb_id, session_id, content_type, source, content, vec_str)
                )
            conn.commit()
        return emb_id

    def store_chat_message_embed(self, session_id: str, role: str, content: str):
        return self.store_embedding(session_id, "history", f"{role}: {content}", role)

    def store_evidence_embed(self, session_id: str, source: str, text: str):
        return self.store_embedding(session_id, "evidence", text, source)

    def search_embeddings(self, query: str, content_type: Optional[str] = None, session_id: Optional[str] = None, top_k: int = 5, threshold: float = 0.5) -> list[dict]:
        query_emb = self._embed(query)
        if query_emb is None:
            return []

        where_clauses = []
        params = []
        if content_type:
            where_clauses.append("content_type = %s")
            params.append(content_type)
        if session_id:
            where_clauses.append("session_id = %s")
            params.append(session_id)

        # Distance <= (1 - threshold)
        dist_threshold = 1.0 - threshold
        where_clauses.append("embedding <=> %s <= %s")
        vec_str = f"[{','.join(map(str, query_emb))}]"
        params.extend([vec_str, dist_threshold])

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        sql = f"""
            SELECT id, session_id, content_type, source, content,
                   1 - (embedding <=> %s) as score
            FROM embeddings
            {where_sql}
            ORDER BY embedding <=> %s
            LIMIT %s
        """
        final_params = [vec_str] + params + [vec_str, top_k]

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, tuple(final_params))
                rows = cur.fetchall()

        # Convert RealDictRow to standard dict and score to float
        return [{
            "id": r["id"],
            "session_id": r["session_id"],
            "content_type": r["content_type"],
            "source": r["source"],
            "content": r["content"],
            "score": float(r["score"])
        } for r in rows]

    def search_history(self, query: str, session_id: Optional[str] = None, top_k: int = 3) -> list[dict]:
        return self.search_embeddings(query, content_type="history", session_id=session_id, top_k=top_k)

    def search_evidence(self, query: str, session_id: Optional[str] = None, top_k: int = 5) -> list[dict]:
        return self.search_embeddings(query, content_type="evidence", session_id=session_id, top_k=top_k)
