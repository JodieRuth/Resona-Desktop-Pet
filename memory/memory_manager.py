import os
import json
import sqlite3
import uuid
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any

from memory.vector_store import VectorStore

logger = logging.getLogger("Memory")


class MemoryManager:
    def __init__(self, project_root: Path, config_manager):
        self.project_root = project_root
        self.config = config_manager
        self.memory_dir = project_root / "memory"
        self.db_dir = self.memory_dir / "db"
        self.temp_session_file = self.memory_dir / "temp_session.json"

        self.memory_dir.mkdir(exist_ok=True)
        self.db_dir.mkdir(exist_ok=True)

        self.soul_content = self._load_soul_content()
        self.vector_store = self._init_vector_store()

    def _init_vector_store(self) -> Optional[VectorStore]:
        if not self.config.getboolean("Memory", "vector_enabled", fallback=False):
            return None

        model_path = self.project_root / self.config.get("Memory", "vector_model_path", fallback="memory/sentence-transformers")
        model_file = self.config.get("Memory", "vector_model_file", fallback="model.onnx")

        logger.info(f"[MemoryManager] Initializing vector store...")
        store = VectorStore(model_path, model_file)
        if store.is_loaded():
            logger.info(f"[MemoryManager] Vector store initialized successfully")
            return store
        else:
            logger.warning(f"[MemoryManager] Vector store failed to initialize")
        return None
    
    def _load_soul_content(self) -> str:
        soul_file = self.memory_dir / "soul.md"
        if soul_file.exists():
            try:
                return soul_file.read_text(encoding="utf-8")
            except Exception:
                return ""
        return ""
    
    def get_soul_content(self, pack_id: Optional[str] = None) -> str:
        return self.soul_content
    
    def get_db_path(self, pack_id: str, db_type: str) -> Path:
        if not self.config.getboolean("Memory", "per_pack_memory", fallback=True):
            pack_id = "default"
        
        if db_type == "vector":
            return self.db_dir / f"{pack_id}_memory.db"
        elif db_type == "conversation":
            return self.db_dir / f"{pack_id}_conversations.db"
        else:
            raise ValueError(f"Unknown db_type: {db_type}")
    
    def _get_connection(self, db_path: Path) -> sqlite3.Connection:
        db_path.parent.mkdir(exist_ok=True, parents=True)
        conn = sqlite3.connect(db_path)
        self._initialize_db(conn, db_path)
        return conn
    
    def _initialize_db(self, conn: sqlite3.Connection, db_path: Path):
        cursor = conn.cursor()
        
        if "memory.db" in str(db_path):
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS memory_vectors (
                    uuid TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    vector BLOB,
                    timestamp REAL NOT NULL,
                    session_id TEXT NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_memory_timestamp 
                ON memory_vectors (timestamp DESC)
            ''')
        
        elif "conversations.db" in str(db_path):
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    uuid TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    user_message TEXT NOT NULL,
                    llm_response TEXT NOT NULL,
                    pack_id TEXT NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_conversation_timestamp 
                ON conversations (timestamp DESC)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_conversation_session 
                ON conversations (session_id)
            ''')
        
        conn.commit()
    
    def store_memory(self, pack_id: str, content: str, session_id: str) -> str:
        memory_uuid = str(uuid.uuid4())
        timestamp = time.time()

        if self.vector_store and self.vector_store.is_loaded():
            try:
                vec = self.vector_store.encode_single(content)
                vector = self.vector_store.to_bytes(vec)
            except Exception as e:
                logger.warning(f"[Memory] Vector encoding failed: {e}")
                vector = b""
        else:
            vector = b""

        db_path = self.get_db_path(pack_id, "vector")
        with self._get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO memory_vectors (uuid, content, vector, timestamp, session_id) VALUES (?, ?, ?, ?, ?)",
                (memory_uuid, content, vector, timestamp, session_id)
            )
            conn.commit()

        return memory_uuid
    
    def store_conversation(self, pack_id: str, user_message: str, llm_response: str, session_id: str) -> str:
        conversation_uuid = str(uuid.uuid4())
        timestamp = time.time()

        db_path = self.get_db_path(pack_id, "conversation")
        with self._get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO conversations (uuid, session_id, timestamp, user_message, llm_response, pack_id) VALUES (?, ?, ?, ?, ?, ?)",
                (conversation_uuid, session_id, timestamp, user_message, llm_response, pack_id)
            )
            conn.commit()

        self._cleanup_old_conversations(pack_id)

        return conversation_uuid

    def _cleanup_old_conversations(self, pack_id: str):
        retention_days = self.config.getint("Memory", "conversation_retention_days", fallback=30)

        if retention_days <= 0:
            return

        cutoff_time = time.time() - (retention_days * 24 * 60 * 60)
        db_path = self.get_db_path(pack_id, "conversation")

        if not db_path.exists():
            return

        try:
            with self._get_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM conversations WHERE timestamp < ?",
                    (cutoff_time,)
                )
                deleted_count = cursor.rowcount
                conn.commit()

                if deleted_count > 0:
                    logger.info(f"[Memory] Cleaned up {deleted_count} old conversations (older than {retention_days} days) for pack: {pack_id}")
        except Exception as e:
            logger.error(f"[Memory] Error cleaning up old conversations: {e}")
    
    def delete_memory(self, pack_id: str, memory_uuid: str) -> bool:
        db_path = self.get_db_path(pack_id, "vector")
        with self._get_connection(db_path) as conn:
            cursor = conn.cursor()
            result = cursor.execute(
                "DELETE FROM memory_vectors WHERE uuid = ?",
                (memory_uuid,)
            )
            conn.commit()
            return result.rowcount > 0
    
    def update_memory(self, pack_id: str, memory_uuid: str, content: str) -> bool:
        db_path = self.get_db_path(pack_id, "vector")
        with self._get_connection(db_path) as conn:
            cursor = conn.cursor()
            result = cursor.execute(
                "UPDATE memory_vectors SET content = ?, timestamp = ? WHERE uuid = ?",
                (content, time.time(), memory_uuid)
            )
            conn.commit()
            return result.rowcount > 0
    
    def search_memories(self, pack_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        db_path = self.get_db_path(pack_id, "vector")

        if not query or query.strip() in ['*', 'all', '全部', '所有']:
            with self._get_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT uuid, content, timestamp, session_id FROM memory_vectors ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                )
                results = cursor.fetchall()
        elif self.vector_store and self.vector_store.is_loaded():
            return self._vector_search(pack_id, query, limit)
        else:
            keywords = [k.strip() for k in query.split() if k.strip()]

            with self._get_connection(db_path) as conn:
                cursor = conn.cursor()

                if len(keywords) == 1:
                    cursor.execute(
                        "SELECT uuid, content, timestamp, session_id FROM memory_vectors WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
                        (f"%{query}%", limit)
                    )
                    results = cursor.fetchall()
                else:
                    conditions = " OR ".join(["content LIKE ?"] * len(keywords))
                    params = [f"%{k}%" for k in keywords] + [limit]
                    cursor.execute(
                        f"SELECT uuid, content, timestamp, session_id FROM memory_vectors WHERE {conditions} ORDER BY timestamp DESC LIMIT ?",
                        params
                    )
                    results = cursor.fetchall()

        memories = [
            {
                "uuid": row[0],
                "content": row[1],
                "timestamp": row[2],
                "session_id": row[3]
            }
            for row in results
        ]

        seen_topics = {}
        resolved_memories = []

        for memory in memories:
            content = memory["content"]
            topic = " ".join(content.split()[:3])

            if topic not in seen_topics:
                seen_topics[topic] = memory
                resolved_memories.append(memory)
            else:
                if memory["timestamp"] > seen_topics[topic]["timestamp"]:
                    seen_topics[topic] = memory
                    for i, mem in enumerate(resolved_memories):
                        if mem["content"].startswith(topic):
                            resolved_memories[i] = memory
                            break

        return resolved_memories

    def _vector_search(self, pack_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        db_path = self.get_db_path(pack_id, "vector")

        with self._get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT uuid, content, vector, timestamp, session_id FROM memory_vectors WHERE vector IS NOT NULL AND LENGTH(vector) > 0"
            )
            all_memories = cursor.fetchall()

        if not all_memories:
            return []

        candidates = [(row[1], row[2]) for row in all_memories if row[2]]
        similar = self.vector_store.search_similar(query, candidates, limit)

        content_to_row = {row[1]: row for row in all_memories}
        results = []
        for content, score in similar:
            if content in content_to_row:
                row = content_to_row[content]
                results.append({
                    "uuid": row[0],
                    "content": row[1],
                    "timestamp": row[3],
                    "session_id": row[4],
                    "similarity": score
                })

        return results
    
    def get_conversations(self, pack_id: str, session_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        db_path = self.get_db_path(pack_id, "conversation")
        with self._get_connection(db_path) as conn:
            cursor = conn.cursor()
            
            if session_id:
                cursor.execute(
                    "SELECT uuid, session_id, timestamp, user_message, llm_response FROM conversations WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (session_id, limit)
                )
            else:
                cursor.execute(
                    "SELECT uuid, session_id, timestamp, user_message, llm_response FROM conversations ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                )
            
            results = cursor.fetchall()
        
        return [
            {
                "uuid": row[0],
                "session_id": row[1],
                "timestamp": row[2],
                "user_message": row[3],
                "llm_response": row[4]
            }
            for row in results
        ]
    
    def save_temp_session(self, user_message: str, llm_response: str):
        session_entry = {
            "user_message": user_message,
            "llm_response": llm_response,
            "timestamp": time.time()
        }

        sessions = []
        if self.temp_session_file.exists():
            try:
                with open(self.temp_session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        sessions = data
                    else:
                        sessions = [data]
            except Exception:
                sessions = []

        sessions.append(session_entry)

        with open(self.temp_session_file, "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=2)

    def load_temp_session(self) -> Optional[List[Dict[str, Any]]]:
        if not self.temp_session_file.exists():
            return None

        try:
            with open(self.temp_session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                else:
                    return [data]
        except Exception:
            return None
    
    def delete_temp_session(self):
        if self.temp_session_file.exists():
            try:
                self.temp_session_file.unlink()
            except Exception:
                pass
    
    def get_memory_tools(self, pack_id: str) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "memory_store",
                    "description": "Store a memory in the long-term memory database. Use this for important information that should be remembered.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "The content of the memory to store"
                            },
                            "tags": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": "Optional tags for the memory"
                            },
                            "importance": {
                                "type": "number",
                                "description": "Importance score (0-1) for the memory"
                            }
                        },
                        "required": ["content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_delete",
                    "description": "Delete a memory from the long-term memory database.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "uuid": {
                                "type": "string",
                                "description": "The UUID of the memory to delete"
                            }
                        },
                        "required": ["uuid"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_update",
                    "description": "Update a memory in the long-term memory database.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "uuid": {
                                "type": "string",
                                "description": "The UUID of the memory to update"
                            },
                            "content": {
                                "type": "string",
                                "description": "The new content for the memory"
                            }
                        },
                        "required": ["uuid", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_search",
                    "description": "Search memories in the long-term memory database using semantic similarity when vector store is enabled, or keyword matching otherwise. Use '*' or 'all' as query to list all memories.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query to find relevant memories. Use '*' or 'all' to get all memories. When vector store is enabled, this uses semantic similarity search."
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results to return (default: 5)"
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]
