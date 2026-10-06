"""
app/models.py - Pydantic Data Models for NetScope Control Plane
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ClientRole(str, Enum):
    UNSET = "unset"
    SEND = "send"
    RECEIVE = "receive"


class ClientStatus(str, Enum):
    CONNECTED = "connected"
    WAITING = "waiting"
    PAIRING = "pairing"
    PAIRED = "paired"
    TRANSFERRING = "transferring"
    COMPLETED = "completed"
    DISCONNECTED = "disconnected"


class PairStatus(str, Enum):
    CONNECTED = "CONNECTED"
    ROLE_SELECTED = "ROLE_SELECTED"
    WAITING_FOR_PEER = "WAITING_FOR_PEER"
    PAIRING = "PAIRING"
    PAIRED = "PAIRED"
    TCP_CONNECTING = "TCP_CONNECTING"
    TRANSFERRING = "TRANSFERRING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DISCONNECTED = "DISCONNECTED"


class ClientInfo(BaseModel):
    client_id: str
    client_name: str
    ip: str
    role: ClientRole = ClientRole.UNSET
    status: ClientStatus = ClientStatus.CONNECTED
    online: bool = True
    joined_at: str
    last_seen: float


class PairInfo(BaseModel):
    pair_id: str
    session_id: str
    sender_id: str
    sender_name: str
    sender_ip: str
    receiver_id: str
    receiver_name: str
    receiver_ip: str
    receiver_port: int = 5000
    status: PairStatus = PairStatus.PAIRED
    created_at: str
    updated_at: str


class SessionInfo(BaseModel):
    session_id: str
    join_url: str
    server_ip: str
    status: str = "ACTIVE"
    created_at: str
    clients: Dict[str, ClientInfo] = Field(default_factory=dict)
    active_pair: Optional[PairInfo] = None
    uploaded_file: Optional[str] = None  # Absolute path to the sender-uploaded file for this session
    sender_file_path: Optional[str] = None


class ClientJoinRequest(BaseModel):
    client_name: str
    role: Optional[str] = "unset"  # send, receive, or unset


class RoleSelectRequest(BaseModel):
    client_id: str
    role: str  # send or receive


class ImpairRequest(BaseModel):
    delay: Optional[str] = "0ms"
    loss: Optional[str] = "0%"
    rate: Optional[str] = "Unlimited"


class TransferRequest(BaseModel):
    mode: str = "send"
    file: Optional[str] = None
    scenario: Optional[str] = "Manual"
    pair_id: Optional[str] = None
    session_id: Optional[str] = None


class TransferProgressReport(BaseModel):
    transfer_id: str
    pair_id: str
    pct: float
    bytes_sent: int
    total_bytes: int
    mbps: float
    rtt_ms: Optional[float] = None
