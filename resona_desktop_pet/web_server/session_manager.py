import uuid
import time
from typing import Dict, Optional
from fastapi import WebSocket
from ..backend.llm_backend import ConversationHistory

class ClientSession:
    def __init__(self, session_id: str, pack_id: str, history_max_rounds: int):
        self.session_id = session_id
        self.pack_id = pack_id
        self.client_type = "unknown"
        self.outfit = None  
        self.history = ConversationHistory(max_rounds=history_max_rounds)
        self.last_active = time.time()
        self.websocket: Optional[WebSocket] = None
        self.settings = {}

    def touch(self):
        self.last_active = time.time()

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}

    def create_session(self, pack_id: str, max_rounds: int) -> ClientSession:
        sid = str(uuid.uuid4())
        session = ClientSession(sid, pack_id, max_rounds)
        self.sessions[sid] = session
        return session

    def get_session(self, sid: str) -> Optional[ClientSession]:
        return self.sessions.get(sid)
    
    async def broadcast_to_pack(self, pack_id: str, message: dict):
        for session in self.sessions.values():
            if session.pack_id == pack_id and session.websocket:
                try:
                    await session.websocket.send_json(message)
                except Exception:
                    pass

    async def broadcast_all(self, message: dict):
        for session in self.sessions.values():
            if session.websocket:
                try:
                    await session.websocket.send_json(message)
                except Exception:
                    pass
