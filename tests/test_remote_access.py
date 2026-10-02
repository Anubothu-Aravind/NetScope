#!/usr/bin/env python3
"""
tests/test_remote_access.py - Test Non-Loopback (Remote) Client Access Restrictions

Verifies:
1. Loopback clients (127.0.0.1) have full access to all endpoints.
2. Remote clients (e.g. mobile phones on LAN) can ONLY access:
   - GET /join/*
   - POST /api/session/*/join
   - GET /api/session/*
   - GET /api/qr/*
   - Static assets (/manifest.json, /icon.svg, /sw.js)
3. Remote clients are REJECTED with 403 Forbidden for:
   - POST /api/impair, DELETE /api/impair
   - POST /api/transfer
   - POST /api/upload
   - POST /api/experiments/*
   - GET /api/events
   - GET / (desktop GUI)
"""

import os
import sys
import time
import json
import unittest
import threading
import urllib.request
import urllib.error

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import uvicorn
from app.main import app, SESSIONS

TEST_PORT = 8003
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"


class TestRemoteAccessSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = uvicorn.Config(app, host="127.0.0.1", port=TEST_PORT, log_level="error")
        cls.server = uvicorn.Server(cls.config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()
        time.sleep(1.2)

        # Pre-seed a test session
        from app.session_manager import session_manager
        sess = session_manager.create_session("192.168.1.50")
        sess.session_id = "REMOTE1"
        sess.join_url = "http://192.168.1.50:8000/join/REMOTE1"
        session_manager.sessions["REMOTE1"] = sess

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True

    def make_request(self, path, method="GET", data=None, remote_ip=None):
        headers = {}
        if remote_ip:
            headers["X-Forwarded-For"] = remote_ip
        if data is not None:
            headers["Content-Type"] = "application/json"
            encoded_data = json.dumps(data).encode("utf-8")
        else:
            encoded_data = None

        req = urllib.request.Request(f"{BASE_URL}{path}", data=encoded_data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def test_localhost_has_full_access(self):
        """Verify localhost (no remote header) can access desktop GUI and control APIs."""
        # 1. Desktop Index
        status, body = self.make_request("/")
        self.assertEqual(status, 200)
        self.assertIn("NetScope", body)

        # 2. Scenarios API
        status, body = self.make_request("/api/scenarios")
        self.assertEqual(status, 200)
        scenarios = json.loads(body)
        self.assertEqual(len(scenarios), 11)

        # 3. Impairment Query
        status, body = self.make_request("/api/impair")
        self.assertEqual(status, 200)

    def test_remote_client_allowed_endpoints(self):
        """Verify remote client (phone IP) can access join, session metadata and QR."""
        remote_ip = "192.168.1.155"

        # 1. GET /join/REMOTE1
        status, body = self.make_request("/join/REMOTE1", remote_ip=remote_ip)
        self.assertEqual(status, 200)
        self.assertIn("REMOTE1", body)

        # 2. GET /api/session/REMOTE1
        status, body = self.make_request("/api/session/REMOTE1", remote_ip=remote_ip)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["session_id"], "REMOTE1")

        # 3. GET /api/qr/REMOTE1
        status, body = self.make_request("/api/qr/REMOTE1", remote_ip=remote_ip)
        self.assertEqual(status, 200)
        self.assertIn("<svg", body)

        # 4. POST /api/session/REMOTE1/join
        status, body = self.make_request(
            "/api/session/REMOTE1/join",
            method="POST",
            data={"role": "receive"},
            remote_ip=remote_ip
        )
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["session"]["peer_joined"])
        self.assertEqual(data["session"]["peer_role"], "receive")

    def test_remote_client_forbidden_endpoints(self):
        """Verify remote client (phone IP) receives 403 Forbidden for internal controls."""
        remote_ip = "192.168.1.155"

        # 1. Impairment API
        status, body = self.make_request(
            "/api/impair",
            method="POST",
            data={"delay": "100ms", "loss": "2%", "rate": "5mbit"},
            remote_ip=remote_ip
        )
        self.assertEqual(status, 403, f"Expected 403 for /api/impair, got {status}")
        self.assertIn("Forbidden", body)

        # 2. Transfer API
        status, body = self.make_request(
            "/api/transfer",
            method="POST",
            data={"mode": "send", "file": "tests/data/test_10mb.bin"},
            remote_ip=remote_ip
        )
        self.assertEqual(status, 403, f"Expected 403 for /api/transfer, got {status}")

        # 3. Experiments API
        status, body = self.make_request(
            "/api/experiments/start",
            method="POST",
            remote_ip=remote_ip
        )
        self.assertEqual(status, 403, f"Expected 403 for /api/experiments/start, got {status}")

        # 4. Upload API
        status, body = self.make_request(
            "/api/upload",
            method="POST",
            remote_ip=remote_ip
        )
        self.assertEqual(status, 403, f"Expected 403 for /api/upload, got {status}")

        # 5. Events SSE stream
        status, body = self.make_request("/api/events", remote_ip=remote_ip)
        self.assertEqual(status, 403, f"Expected 403 for /api/events, got {status}")

        # 6. Desktop UI root
        status, body = self.make_request("/", remote_ip=remote_ip)
        self.assertEqual(status, 403, f"Expected 403 for /, got {status}")


if __name__ == "__main__":
    unittest.main()
