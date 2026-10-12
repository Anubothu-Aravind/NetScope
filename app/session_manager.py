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

    def is_client_active(self, client: ClientInfo, timeout_seconds: float = 45.0) -> bool:
        """Check if client is currently online and within heartbeat window."""
        return bool(client.online and (time.time() - client.last_seen < timeout_seconds))

    def cleanup_stale_clients(self, session_id: str, timeout_seconds: float = 45.0) -> List[str]:
        """Mark clients whose last_seen exceeds timeout as offline."""
        session = self.get_session(session_id)
        if not session:
            return []
        stale_ids = []
        now = time.time()
        for cid, c in list(session.clients.items()):
            if c.online and (now - c.last_seen > timeout_seconds):
                c.online = False
                c.status = ClientStatus.DISCONNECTED
                stale_ids.append(cid)
        return stale_ids

    def register_client(
        self,
        session_id: str,
        client_name: str,
        ip: str,
        role_str: str = "unset",
        client_id: Optional[str] = None
    ) -> ClientInfo:
        """Register a new device or reconnect an existing device in the session."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Session {session_id} not found")

        # Cleanup stale clients before evaluating roles
        self.cleanup_stale_clients(session_id)

        # 1. Check if client is reconnecting with an existing client_id
        if client_id and client_id in session.clients:
            existing = session.clients[client_id]
            existing.online = True
            existing.last_seen = time.time()
            existing.ip = ip
            if client_name.strip():
                existing.client_name = client_name.strip()
            r_str = role_str.lower()
            if r_str in ("send", "sender"):
                existing.role = ClientRole.SEND
            elif r_str in ("receive", "receiver"):
                existing.role = ClientRole.RECEIVE
            elif r_str in [r.value for r in ClientRole]:
                existing.role = ClientRole(r_str)
            if existing.status == ClientStatus.DISCONNECTED:
                existing.status = ClientStatus.WAITING
            return existing

        # 2. Create fresh client registration
        new_client_id = client_id or f"C-{uuid.uuid4().hex[:6].upper()}"
        r_str = role_str.lower()
        if r_str == "auto":
            has_sender = any(c.role == ClientRole.SEND for c in session.clients.values() if self.is_client_active(c))
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
            client_id=new_client_id,
            client_name=client_name.strip() or f"Client-{new_client_id}",
            ip=ip,
            role=role,
            status=status,
            online=True,
            joined_at=datetime.now(timezone.utc).isoformat(),
            last_seen=time.time()
        )
        session.clients[new_client_id] = client
        return client

    def reconnect_client(self, session_id: str, client_id: str, ip: Optional[str] = None) -> Optional[ClientInfo]:
        """Restore active state for a reconnecting client."""
        client = self.get_client(session_id, client_id)
        if client:
            client.online = True
            client.last_seen = time.time()
            if ip:
                client.ip = ip
            if client.status == ClientStatus.DISCONNECTED:
                client.status = ClientStatus.WAITING
            return client
        return None

    def reset_session(self, session_id: str) -> Optional[SessionInfo]:
        """Reset session transfer and pairing state to allow repeated runs."""
        session = self.get_session(session_id)
        if not session:
            return None

        session.uploaded_file = None
        session.sender_file_path = None
        session.payload_size = None
        session.sender_filename = None
        session.sender_ready = False
        session.active_pair = None

        now = time.time()
        for client in session.clients.values():
            if self.is_client_active(client):
                client.status = ClientStatus.WAITING
                client.last_seen = now

        return session

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
        self.cleanup_stale_clients(session_id)
        return list(session.clients.values())


# Global singleton instance
session_manager = SessionManager()

