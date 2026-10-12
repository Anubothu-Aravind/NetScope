#!/usr/bin/env python3
"""
tests/test_retransmissions_and_ladder.py
Regression tests for TCP packet loss emulation, RTO timeouts, retransmissions,
retry sequencing, and timeline replay data structures.
"""

import os
import sys
import tempfile
import threading
import time
import socket
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from common.protocol import send_file_stream, recv_file_stream, compute_sha256, get_default_port
from server.tcp_server import TCPServer


class TestRetransmissionsAndLadder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="netscope_retrans_")
        cls.file_size = 256 * 1024  # 256 KB (4 chunks of 64KB)
        cls.test_file = os.path.join(cls.test_dir, "test_file.bin")
        with open(cls.test_file, "wb") as f:
            f.write(os.urandom(cls.file_size))
        cls.expected_sha = compute_sha256(cls.test_file)

    def test_retransmissions_under_loss(self):
        """Verify that packet loss triggers packet_loss, timeout, and retransmission events with retry counts."""
        events_emitted = []

        def capture_stats(stats):
            if stats.get("event"):
                events_emitted.append(dict(stats))

        # Spin up a simple receiving socket in thread
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]

        rx_data = bytearray()
        def rx_worker():
            conn, _ = server_sock.accept()
            while len(rx_data) < self.file_size:
                c = conn.recv(65536)
                if not c:
                    break
                rx_data.extend(c)
            conn.close()

        rx_th = threading.Thread(target=rx_worker, daemon=True)
        rx_th.start()

        # Connect client and send with 50% simulated loss
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect(("127.0.0.1", port))

        actual_sha = send_file_stream(
            client_sock,
            self.test_file,
            self.file_size,
            delay_ms=5.0,
            loss_pct=50.0,
            rate_bps=0.0,
            stats_cb=capture_stats
        )
        client_sock.close()
        rx_th.join(timeout=3.0)
        server_sock.close()

        # Integrity verified despite loss and retransmissions
        self.assertEqual(actual_sha, self.expected_sha)
        self.assertEqual(len(rx_data), self.file_size)

        # Check emitted retransmission events
        loss_events = [e for e in events_emitted if e.get("event") == "packet_loss"]
        timeout_events = [e for e in events_emitted if e.get("event") == "timeout"]
        retrans_events = [e for e in events_emitted if e.get("event") == "retransmission"]

        self.assertGreater(len(loss_events), 0, "Expected at least one packet_loss event")
        self.assertGreater(len(timeout_events), 0, "Expected at least one timeout event")
        self.assertGreater(len(retrans_events), 0, "Expected at least one retransmission event")

        # Verify retry counts and sequence numbers
        for r_ev in retrans_events:
            self.assertIn("seq", r_ev)
            self.assertIn("retry", r_ev)
            self.assertGreaterEqual(r_ev["retry"], 1)

    def test_fine_grained_pacing_responsiveness(self):
        """Verify that bandwidth pacing emits intermediate ticks and keeps UI alive."""
        pacing_events = []

        def capture_stats(stats):
            if stats.get("event") == "pacing":
                pacing_events.append(dict(stats))

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]

        def rx_worker():
            conn, _ = server_sock.accept()
            while True:
                c = conn.recv(65536)
                if not c:
                    break
            conn.close()

        rx_th = threading.Thread(target=rx_worker, daemon=True)
        rx_th.start()

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect(("127.0.0.1", port))

        # Pace at 2 Mbps (~1.0s transfer time for 256 KB)
        send_file_stream(
            client_sock,
            self.test_file,
            self.file_size,
            delay_ms=0.0,
            loss_pct=0.0,
            rate_bps=2_000_000.0,  # 2 Mbps
            stats_cb=capture_stats
        )
        client_sock.close()
        rx_th.join(timeout=3.0)
        server_sock.close()

        self.assertGreater(len(pacing_events), 5, "Expected sliced pacing events to keep UI responsive")


if __name__ == "__main__":
    unittest.main()
