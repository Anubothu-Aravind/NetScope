#!/usr/bin/env python3
"""
tests/test_session_lifecycle.py - Automated Unit Tests for Session Resumption, Stale Slot Cleanup & Reset
"""

import unittest
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.session_manager import SessionManager
from app.pairing_manager import PairingManager
from app.models import ClientRole, ClientStatus, PairStatus
from app.main import ensure_sample_payload


class TestSessionLifecycle(unittest.TestCase):
    def setUp(self):
        self.sm = SessionManager()

    def test_client_reconnection_preserves_slot(self):
        sess = self.sm.create_session("127.0.0.1", 8000)
        sid = sess.session_id

        # 1. Client registers as receiver
        c1 = self.sm.register_client(sid, "Mobile-Receiver", "192.168.1.50", "receive")
        cid = c1.client_id
        self.assertEqual(c1.role, ClientRole.RECEIVE)
        self.assertTrue(c1.online)

        # 2. Client refreshes browser and reconnects using the same client_id
        c2 = self.sm.register_client(sid, "Mobile-Receiver", "192.168.1.50", "receive", client_id=cid)
        self.assertEqual(c2.client_id, cid)
        self.assertEqual(c2.role, ClientRole.RECEIVE)
        self.assertTrue(c2.online)
        self.assertEqual(len(self.sm.list_clients(sid)), 1)

    def test_stale_client_cleanup_after_inactivity(self):
        sess = self.sm.create_session("127.0.0.1", 8000)
        sid = sess.session_id

        c = self.sm.register_client(sid, "Mobile-Old", "192.168.1.60", "send")
        self.assertTrue(self.sm.is_client_active(c))

        # Simulate 50 seconds of inactivity
        c.last_seen = time.time() - 50.0
        self.assertFalse(self.sm.is_client_active(c))

        stale = self.sm.cleanup_stale_clients(sid, timeout_seconds=45.0)
        self.assertIn(c.client_id, stale)
        self.assertFalse(c.online)
        self.assertEqual(c.status, ClientStatus.DISCONNECTED)

    def test_session_reset_lifecycle(self):
        sess = self.sm.create_session("127.0.0.1", 8000)
        sid = sess.session_id

        c_send = self.sm.register_client(sid, "Host-Sender", "127.0.0.1", "send")
        c_recv = self.sm.register_client(sid, "Phone-Recv", "192.168.1.70", "receive")

        # Simulate active pair and transfer completed
        c_send.status = ClientStatus.COMPLETED
        c_recv.status = ClientStatus.COMPLETED
        sess.uploaded_file = "/tmp/test.bin"

        # Host clicks Run Another -> reset_session
        reset_sess = self.sm.reset_session(sid)
        self.assertIsNone(reset_sess.uploaded_file)
        self.assertIsNone(reset_sess.active_pair)
        self.assertEqual(c_send.status, ClientStatus.WAITING)
        self.assertEqual(c_recv.status, ClientStatus.WAITING)

    def test_sample_payload_generation(self):
        # Test deterministic binary generation for 1MB, 10MB, 50MB
        p1 = ensure_sample_payload("1MB")
        self.assertTrue(os.path.isfile(p1))
        self.assertEqual(os.path.getsize(p1), 1048576)

        p10 = ensure_sample_payload("10MB")
        self.assertTrue(os.path.isfile(p10))
        self.assertEqual(os.path.getsize(p10), 10485760)

        p50 = ensure_sample_payload("50MB")
        self.assertTrue(os.path.isfile(p50))
        self.assertEqual(os.path.getsize(p50), 52428800)


    def test_client_payload_ready_signaling(self):
        import asyncio
        from app.main import signal_sender_ready, TransferRequest, session_manager

        sess = session_manager.create_session("127.0.0.1", 8000)
        sid = sess.session_id

        # Client selects 10MB deterministic payload
        asyncio.run(signal_sender_ready(sid, {"payload_size": "10MB", "filename": "sample_10mb.bin"}))
        self.assertEqual(sess.payload_size, "10MB")
        self.assertTrue(os.path.isfile(sess.sender_file_path))
        self.assertEqual(os.path.getsize(sess.sender_file_path), 10485760)

        # TransferRequest without payload_size attribute operates cleanly without AttributeError
        req = TransferRequest(mode="send", scenario="Manual", session_id=sid)
        self.assertIsNone(req.payload_size)
        self.assertIsNone(getattr(req, "payload_size", None))


if __name__ == "__main__":
    unittest.main()

