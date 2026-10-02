"""
app/pairing_manager.py - Deterministic Client Pairing Engine and State Machine
"""

import time
import threading
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timezone

from app.models import (
    PairInfo,
    PairStatus,
    ClientRole,
    ClientStatus,
    ClientInfo,
    SessionInfo
)
from app.session_manager import session_manager


class PairingManager:
    """Coordinates deterministic pairing of SEND and RECEIVE clients."""

    def __init__(self):
        self._lock = threading.Lock()
        self.pairs: Dict[str, PairInfo] = {}
        self._pair_counter = 1

    def attempt_pairing(self, session_id: str) -> Optional[PairInfo]:
        """
        Evaluate all connected clients in the session.
        If an unpaired SEND client and an unpaired RECEIVE client exist,
        deterministically pair them into a new PairInfo.
        """
        with self._lock:
            session = session_manager.get_session(session_id)
            if not session:
                return None

            # If there is already an active transferring/paired pair, return it
            if session.active_pair and session.active_pair.status in (
                PairStatus.PAIRED,
                PairStatus.TCP_CONNECTING,
                PairStatus.TRANSFERRING
            ):
                return session.active_pair

            # Find candidates
            senders: List[ClientInfo] = []
            receivers: List[ClientInfo] = []

            # Check all clients that are online and not already paired
            paired_client_ids = set()
            for p in self.pairs.values():
                if p.session_id == session.session_id and p.status in (
                    PairStatus.PAIRED,
                    PairStatus.TCP_CONNECTING,
                    PairStatus.TRANSFERRING
                ):
                    paired_client_ids.add(p.sender_id)
                    paired_client_ids.add(p.receiver_id)

            for c in session.clients.values():
                if not c.online or c.client_id in paired_client_ids:
                    continue
                if c.role == ClientRole.SEND:
                    senders.append(c)
                elif c.role == ClientRole.RECEIVE:
                    receivers.append(c)

            # Sort deterministically by join timestamp
            senders.sort(key=lambda x: x.joined_at)
            receivers.sort(key=lambda x: x.joined_at)

            if senders and receivers:
                sender = senders[0]
                receiver = receivers[0]

                pair_id = f"P-{self._pair_counter:03d}"
                self._pair_counter += 1

                now_iso = datetime.now(timezone.utc).isoformat()
                pair = PairInfo(
                    pair_id=pair_id,
                    session_id=session.session_id,
                    sender_id=sender.client_id,
                    sender_name=sender.client_name,
                    sender_ip=sender.ip,
                    receiver_id=receiver.client_id,
                    receiver_name=receiver.client_name,
                    receiver_ip=receiver.ip,
                    receiver_port=5000,
                    status=PairStatus.PAIRED,
                    created_at=now_iso,
                    updated_at=now_iso
                )

                sender.status = ClientStatus.PAIRED
                receiver.status = ClientStatus.PAIRED

                self.pairs[pair_id] = pair
                session.active_pair = pair
                return pair

            return None

    def get_pair(self, pair_id: str) -> Optional[PairInfo]:
        return self.pairs.get(pair_id)

    def get_client_pair(self, session_id: str, client_id: str) -> Optional[PairInfo]:
        """Find active pair associated with a given client."""
        for p in self.pairs.values():
            if p.session_id == session_id and (p.sender_id == client_id or p.receiver_id == client_id):
                if p.status not in (PairStatus.COMPLETED, PairStatus.FAILED, PairStatus.CANCELLED):
                    return p
        return None

    def get_session_pairs(self, session_id: str) -> List[PairInfo]:
        """Return all pairs in this session, latest first."""
        matching = [p for p in self.pairs.values() if p.session_id == session_id]
        matching.sort(key=lambda x: x.created_at, reverse=True)
        return matching

    def update_pair_status(self, pair_id: str, new_status: PairStatus) -> Optional[PairInfo]:
        """Transition pair state machine."""
        with self._lock:
            pair = self.pairs.get(pair_id)
            if not pair:
                return None

            pair.status = new_status
            pair.updated_at = datetime.now(timezone.utc).isoformat()

            # Update client statuses in session
            session = session_manager.get_session(pair.session_id)
            if session:
                sender = session.clients.get(pair.sender_id)
                receiver = session.clients.get(pair.receiver_id)

                if new_status == PairStatus.TRANSFERRING:
                    if sender: sender.status = ClientStatus.TRANSFERRING
                    if receiver: receiver.status = ClientStatus.TRANSFERRING
                elif new_status == PairStatus.COMPLETED:
                    if sender: sender.status = ClientStatus.COMPLETED
                    if receiver: receiver.status = ClientStatus.COMPLETED
                elif new_status in (PairStatus.FAILED, PairStatus.CANCELLED, PairStatus.DISCONNECTED):
                    if sender: sender.status = ClientStatus.WAITING
                    if receiver: receiver.status = ClientStatus.WAITING
                    if session.active_pair and session.active_pair.pair_id == pair_id:
                        session.active_pair = None

            return pair

    def handle_client_disconnect(self, session_id: str, client_id: str):
        """Unpair client if active and transition partner back to waiting."""
        with self._lock:
            pair = self.get_client_pair(session_id, client_id)
            if pair:
                pair.status = PairStatus.DISCONNECTED
                pair.updated_at = datetime.now(timezone.utc).isoformat()

                session = session_manager.get_session(session_id)
                if session:
                    partner_id = pair.receiver_id if pair.sender_id == client_id else pair.sender_id
                    partner = session.clients.get(partner_id)
                    if partner:
                        partner.status = ClientStatus.WAITING
                    if session.active_pair and session.active_pair.pair_id == pair.pair_id:
                        session.active_pair = None


# Global singleton instance
pairing_manager = PairingManager()
