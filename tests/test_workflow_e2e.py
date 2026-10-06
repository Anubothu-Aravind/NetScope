"""
tests/test_workflow_e2e.py - Complete End-to-End Workflow Verification

Simulates the full physical lifecycle:
Server Control Plane (Session -> QR -> Client Join -> Pairing)
-> Peer Data Plane (Direct TCP Handshake -> Chunk Transfer -> SHA-256 Verification -> Telemetry)
"""

import os
import sys
import time
import json
import socket
import unittest
import threading
import tempfile
import urllib.request
import urllib.error

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import uvicorn
from app.main import app
from client.tcp_receiver import TCPReceiver
from client.tcp_sender import TCPSender
from client.integrity import compute_file_sha256

TEST_SERVER_PORT = 8004
BASE_URL = f"http://127.0.0.1:{TEST_SERVER_PORT}"


class TestEndToEndWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = uvicorn.Config(app, host="127.0.0.1", port=TEST_SERVER_PORT, log_level="error")
        cls.server = uvicorn.Server(cls.config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()
        time.sleep(1.2)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.data_port = 5065

        from app.pairing_manager import pairing_manager
        pairing_manager._pair_counter = 1
        pairing_manager.pairs.clear()

        # Generate a test payload (1 MB)
        self.test_file = os.path.join(self.tmp_dir.name, "e2e_payload.bin")
        self.payload_bytes = os.urandom(1024 * 1024)
        with open(self.test_file, "wb") as f:
            f.write(self.payload_bytes)
        self.expected_hash = compute_file_sha256(self.test_file)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _post(self, path: str, data: dict = None):
        body = json.dumps(data or {}).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get(self, path: str):
        req = urllib.request.Request(f"{BASE_URL}{path}", method="GET")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_complete_session_pairing_transfer_workflow(self):
        # 1. Server Creates Session
        sess = self._post("/api/session")
        session_id = sess["session_id"]
        self.assertTrue(session_id.startswith("NS-"))
        self.assertIn(f"/join/{session_id}", sess["join_url"])

        # 2. Client A (Phone-A) joins as SENDER
        client_a = self._post(
            f"/api/session/{session_id}/clients",
            {"client_name": "Phone-A", "role": "send"}
        )
        self.assertEqual(client_a["role"], "send")
        self.assertEqual(client_a["client"]["status"], "waiting")

        # 3. Client B (Laptop-B) joins as RECEIVER
        client_b = self._post(
            f"/api/session/{session_id}/clients",
            {"client_name": "Laptop-B", "role": "receive"}
        )
        self.assertEqual(client_b["role"], "receive")

        # 4. Verify Server Auto-Paired Them into Pair P-001
        pair = self._get(f"/api/session/{session_id}/pair")
        self.assertIsNotNone(pair)
        self.assertEqual(pair["pair_id"], "P-001")
        self.assertEqual(pair["sender_id"], client_a["client_id"])
        self.assertEqual(pair["receiver_id"], client_b["client_id"])
        self.assertEqual(pair["status"], "PAIRED")

        # 5. Direct Peer TCP Data Plane
        # Start Receiver in background thread
        recv_dir = os.path.join(self.tmp_dir.name, "recv_out")
        os.makedirs(recv_dir, exist_ok=True)
        receiver = TCPReceiver(host="127.0.0.1", port=self.data_port, save_dir=recv_dir)
        recv_result = {}
        def run_rx():
            nonlocal recv_result
            recv_result = receiver.listen_once(timeout=5.0)

        recv_thread = threading.Thread(target=run_rx, daemon=True)
        recv_thread.start()
        time.sleep(0.3)  # Wait for receiver socket bind

        # Client A sends payload to Client B
        sender = TCPSender(target_ip="127.0.0.1", target_port=self.data_port)
        tx_stats = sender.send_file(
            filepath=self.test_file,
            transfer_id="T-E2E-001",
            pair_id=pair["pair_id"],
            sender_name=client_a["client_name"],
            receiver_name=client_b["client_name"]
        )
        recv_thread.join(timeout=5.0)

        # 6. Verify Transfer Integrity
        self.assertTrue(tx_stats["sha256_match"])
        self.assertEqual(tx_stats["bytes_sent"], len(self.payload_bytes))
        received_path = os.path.join(recv_dir, os.path.basename(self.test_file))
        self.assertTrue(os.path.isfile(received_path))
        self.assertEqual(compute_file_sha256(received_path), self.expected_hash)

        # 7. Telemetry Reporting to Server Control Plane
        prog_res = self._post(
            f"/api/session/{session_id}/telemetry/progress",
            {
                "transfer_id": "T-E2E-001",
                "pair_id": pair["pair_id"],
                "pct": 100.0,
                "bytes_sent": len(self.payload_bytes),
                "total_bytes": len(self.payload_bytes),
                "mbps": tx_stats["throughput_mbps"],
                "rtt_ms": 1.2
            }
        )
        self.assertEqual(prog_res["status"], "ok")

        # Complete telemetry
        comp_res = self._post(
            f"/api/session/{session_id}/telemetry/complete",
            {
                "session_id": session_id,
                "pair_id": pair["pair_id"],
                "transfer_id": "T-E2E-001",
                "sender": client_a["client_name"],
                "receiver": client_b["client_name"],
                "filename": os.path.basename(self.test_file),
                "file_size": len(self.payload_bytes),
                "throughput": tx_stats["throughput_mbps"],
                "completion_time": tx_stats["transfer_time_s"],
                "sha256_match": True,
                "status": "COMPLETED"
            }
        )
        self.assertEqual(comp_res["status"], "ok")

        # 8. Check that pair status updated
        updated_pair = self._get(f"/api/session/{session_id}/pair")
        self.assertEqual(updated_pair["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
