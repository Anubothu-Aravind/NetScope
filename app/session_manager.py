"""
app/session_manager.py - Session Lifecycle and Client Registration Manager
"""

import time
import uuid
from typing import Dict, Optional, List
from datetime import datetime, timezone

from app.models import SessionInfo, ClientInfo, ClientRole, ClientStatus


class SessionManager:
    """Manages active sessions and registered clients in memory."""

    def __init__(self):
        self.sessions: Dict[str, SessionInfo] = {}

    def create_session(self, lan_ip: str, port: int = 8000) -> SessionInfo:
        """Create a new session with an 'NS-' prefixed 6-character identifier."""
        random_suffix = uuid.uuid4().hex[:6].upper()
        session_id = f"NS-{random_suffix}"
        join_url = f"http://{lan_ip}:{port}/join/{session_id}"

        session = SessionInfo(
            session_id=session_id,
            join_url=join_url,
            server_ip=lan_ip,
            status="ACTIVE",
            created_at=datetime.now(timezone.utc).isoformat(),
            clients={}
        )
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Retrieve session by ID (case-insensitive with NS- prefix support)."""
        sid = session_id.upper()
        if not sid.startswith("NS-"):
            sid = f"NS-{sid}"
        return self.sessions.get(sid) or self.sessions.get(session_id.upper())

    def register_client(self, session_id: str, client_name: str, ip: str, role_str: str = "unset") -> ClientInfo:
        """Register a new device/client in the session."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Session {session_id} not found")

        client_id = f"C-{uuid.uuid4().hex[:6].upper()}"
        r_str = role_str.lower()
        if r_str == "auto":
            has_sender = any(c.role == ClientRole.SEND for c in session.clients.values() if c.online)
            role = ClientRole.RECEIVE if has_sender else ClientRole.SEND
        elif r_str in ("send", "sender"):
            role = ClientRole.SEND
        elif r_str in ("receive", "receiver"):
            role = ClientRole.RECEIVE
        elif r_str in [r.value for r in ClientRole]:
            role = ClientRole(r_str)
        else:
            role = ClientRole.UNSET
        status = ClientStatus.WAITING if role != ClientRole.UNSET else ClientStatus.CONNECTED

        client = ClientInfo(
            client_id=client_id,
            client_name=client_name.strip() or f"Client-{client_id}",
            ip=ip,
            role=role,
            status=status,
            online=True,
            joined_at=datetime.now(timezone.utc).isoformat(),
            last_seen=time.time()
        )
        session.clients[client_id] = client
        return client

    def get_client(self, session_id: str, client_id: str) -> Optional[ClientInfo]:
        session = self.get_session(session_id)
        if not session:
            return None
        return session.clients.get(client_id)

    def remove_client(self, session_id: str, client_id: str) -> Optional[ClientInfo]:
        """Remove a client when they leave or disconnect."""
        session = self.get_session(session_id)
        if not session or client_id not in session.clients:
            return None
        client = session.clients.pop(client_id)
        return client

    def set_client_role(self, session_id: str, client_id: str, role_str: str) -> ClientInfo:
        """Update role for a registered client."""
        client = self.get_client(session_id, client_id)
        if not client:
            raise KeyError(f"Client {client_id} not found in session {session_id}")

        role = ClientRole(role_str.lower())
        client.role = role
        client.status = ClientStatus.WAITING
        client.last_seen = time.time()
        return client

    def update_heartbeat(self, session_id: str, client_id: str):
        """Record activity from client to maintain online state."""
        client = self.get_client(session_id, client_id)
        if client:
            client.last_seen = time.time()
            client.online = True

    def list_clients(self, session_id: str) -> List[ClientInfo]:
        session = self.get_session(session_id)
        if not session:
            return []
        return list(session.clients.values())


# Global singleton instance
session_manager = SessionManager()
