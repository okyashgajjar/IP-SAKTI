import sqlite3
import json
import uuid
import datetime

class LocalDBClient:
    def __init__(self, db_path="database.db"):
        self.db_path = db_path
        self.init_db()
        
    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                )
            ''')
            conn.commit()

    def execute_query(self, query, params=()):
        with sqlite3.connect(self.db_path) as conn:
            # Return rows as dicts
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return [dict(row) for row in cursor.fetchall()]
            
    def create_session_if_not_exists(self, session_id, title="New Chat"):
        # Check if session exists
        res = self.execute_query("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if not res:
            self.execute_query("INSERT INTO sessions (id, title) VALUES (?, ?)", (session_id, title))

    def save_chat_message(self, session_id, role, content):
        self.create_session_if_not_exists(session_id)
        # Update title if it's the first user message
        if role == 'user':
            res = self.execute_query("SELECT count(*) as cnt FROM chat_messages WHERE session_id = ?", (session_id,))
            if res and res[0]['cnt'] == 0:
                # Truncate content for title
                title = content[:30] + '...' if len(content) > 30 else content
                self.execute_query("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))

        msg_id = str(uuid.uuid4())
        self.execute_query(
            "INSERT INTO chat_messages (id, session_id, role, content) VALUES (?, ?, ?, ?)",
            (msg_id, session_id, role, content)
        )

    def get_sessions(self):
        return self.execute_query("SELECT id, title, created_at FROM sessions ORDER BY created_at DESC")

    def get_chat_history(self, session_id):
        return self.execute_query("SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY rowid ASC", (session_id,))
