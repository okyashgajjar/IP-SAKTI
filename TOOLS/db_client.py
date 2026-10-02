import sqlite3
import json

class LocalDBClient:
    def __init__(self, db_path="database.db"):
        self.db_path = db_path
        
    def execute_query(self, query, params=()):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.fetchall()
            
    def save_chat_message(self, session_id, role, content):
        import uuid
        msg_id = str(uuid.uuid4())
        self.execute_query(
            "INSERT INTO chat_messages (id, session_id, role, content) VALUES (?, ?, ?, ?)",
            (msg_id, session_id, role, content)
        )
