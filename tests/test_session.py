#!/usr/bin/env python3
"""
tests/test_session.py - Unit Tests for Session Management & Client Registration
"""

import unittest
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.session_manager import SessionManager
from app.models import ClientRole, ClientStatus


class TestSessionManager(unittest.TestCase):
    def setUp(self):
        self.mgr = SessionManager()

    def test_session_creation(self):
        sess = self.mgr.create_session("192.168.1.100", 8000)
        self.assertTrue(sess.session_id.startswith("NS-"))
        self.assertEqual(len(sess.session_id), 9)  # 'NS-' + 6 chars = 9
        self.assertIn(sess.session_id, sess.join_url)
        self.assertEqual(sess.server_ip, "192.168.1.100")
        self.assertEqual(sess.status, "ACTIVE")

    def test_session_retrieval(self):
        sess = self.mgr.create_session("192.168.1.100")
        sid = sess.session_id

        # Exact match
        self.assertEqual(self.mgr.get_session(sid), sess)
        # Without NS- prefix
        raw_suffix = sid.replace("NS-", "")
        self.assertEqual(self.mgr.get_session(raw_suffix), sess)
        # Lowercase
        self.assertEqual(self.mgr.get_session(sid.lower()), sess)

    def test_client_registration_and_roles(self):
        sess = self.mgr.create_session("192.168.1.100")
        sid = sess.session_id

        # Register client A
        c_a = self.mgr.register_client(sid, "Phone-A", "192.168.1.10", "send")
        self.assertEqual(c_a.client_name, "Phone-A")
        self.assertEqual(c_a.role, ClientRole.SEND)
        self.assertEqual(c_a.status, ClientStatus.WAITING)

        # Register client B
        c_b = self.mgr.register_client(sid, "Laptop-B", "192.168.1.11", "unset")
        self.assertEqual(c_b.role, ClientRole.UNSET)
        self.assertEqual(c_b.status, ClientStatus.CONNECTED)

        # Update role for client B
        self.mgr.set_client_role(sid, c_b.client_id, "receive")
        self.assertEqual(c_b.role, ClientRole.RECEIVE)

        # List clients
        clients = self.mgr.list_clients(sid)
        self.assertEqual(len(clients), 2)

        # Remove client A
        removed = self.mgr.remove_client(sid, c_a.client_id)
        self.assertEqual(removed.client_id, c_a.client_id)
        self.assertEqual(len(self.mgr.list_clients(sid)), 1)


if __name__ == "__main__":
    unittest.main()
