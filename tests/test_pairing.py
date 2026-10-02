#!/usr/bin/env python3
"""
tests/test_pairing.py - Unit Tests for Client Pairing and State Machine
"""

import unittest
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.session_manager import session_manager
from app.pairing_manager import PairingManager
from app.models import PairStatus, ClientStatus, ClientRole


class TestPairingManager(unittest.TestCase):
    def setUp(self):
        # Create fresh session
        self.sess = session_manager.create_session("192.168.1.50")
        self.sid = self.sess.session_id
        self.pm = PairingManager()

    def test_basic_pairing(self):
        # 1. Add Sender
        c_a = session_manager.register_client(self.sid, "Phone-A", "192.168.1.10", "send")
        pair = self.pm.attempt_pairing(self.sid)
        self.assertIsNone(pair, "Should not pair with only a sender")

        # 2. Add Receiver
        c_b = session_manager.register_client(self.sid, "Laptop-B", "192.168.1.11", "receive")
        pair = self.pm.attempt_pairing(self.sid)
        self.assertIsNotNone(pair, "Should pair when sender and receiver are present")
        self.assertEqual(pair.pair_id, "P-001")
        self.assertEqual(pair.sender_id, c_a.client_id)
        self.assertEqual(pair.receiver_id, c_b.client_id)
        self.assertEqual(pair.status, PairStatus.PAIRED)

        # Clients should be marked PAIRED
        self.assertEqual(c_a.status, ClientStatus.PAIRED)
        self.assertEqual(c_b.status, ClientStatus.PAIRED)

    def test_state_machine_transitions(self):
        c_a = session_manager.register_client(self.sid, "Sender-1", "192.168.1.10", "send")
        c_b = session_manager.register_client(self.sid, "Receiver-1", "192.168.1.11", "receive")
        pair = self.pm.attempt_pairing(self.sid)

        # Transition: TCP_CONNECTING
        self.pm.update_pair_status(pair.pair_id, PairStatus.TCP_CONNECTING)
        self.assertEqual(pair.status, PairStatus.TCP_CONNECTING)

        # Transition: TRANSFERRING
        self.pm.update_pair_status(pair.pair_id, PairStatus.TRANSFERRING)
        self.assertEqual(pair.status, PairStatus.TRANSFERRING)
        self.assertEqual(c_a.status, ClientStatus.TRANSFERRING)
        self.assertEqual(c_b.status, ClientStatus.TRANSFERRING)

        # Transition: COMPLETED
        self.pm.update_pair_status(pair.pair_id, PairStatus.COMPLETED)
        self.assertEqual(pair.status, PairStatus.COMPLETED)
        self.assertEqual(c_a.status, ClientStatus.COMPLETED)
        self.assertEqual(c_b.status, ClientStatus.COMPLETED)

    def test_duplicate_prevention(self):
        # Register 1 sender, 2 receivers
        c_a = session_manager.register_client(self.sid, "Sender-A", "192.168.1.10", "send")
        c_b1 = session_manager.register_client(self.sid, "Receiver-1", "192.168.1.11", "receive")
        c_b2 = session_manager.register_client(self.sid, "Receiver-2", "192.168.1.12", "receive")

        pair1 = self.pm.attempt_pairing(self.sid)
        self.assertIsNotNone(pair1)
        self.assertEqual(pair1.receiver_id, c_b1.client_id)

        # Sender-A is already paired; second receiver remains waiting
        pair2 = self.pm.attempt_pairing(self.sid)
        self.assertEqual(pair2.pair_id, pair1.pair_id, "Should return existing active pair")
        self.assertEqual(c_b2.status, ClientStatus.WAITING)

    def test_client_disconnect_handling(self):
        c_a = session_manager.register_client(self.sid, "Sender-A", "192.168.1.10", "send")
        c_b = session_manager.register_client(self.sid, "Receiver-B", "192.168.1.11", "receive")
        pair = self.pm.attempt_pairing(self.sid)
        self.assertEqual(pair.status, PairStatus.PAIRED)

        # Client A leaves
        self.pm.handle_client_disconnect(self.sid, c_a.client_id)
        self.assertEqual(pair.status, PairStatus.DISCONNECTED)
        self.assertEqual(c_b.status, ClientStatus.WAITING, "Partner should revert to waiting")


if __name__ == "__main__":
    unittest.main()
