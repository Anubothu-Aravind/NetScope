#!/usr/bin/env python3
"""
tests/test_transfer.py - Unit Tests for Client-to-Client Direct TCP File Transfer
"""

import unittest
import tempfile
import threading
import shutil
import time
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from client.tcp_receiver import TCPReceiver
from client.tcp_sender import TCPSender
from client.integrity import compute_file_sha256


class TestClientToClientTransfer(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="netscope_c2c_")
        self.receiver_dir = os.path.join(self.test_dir, "received")
        os.makedirs(self.receiver_dir, exist_ok=True)

        # Create 3 MB test file
        self.file_size = 3 * 1024 * 1024
        self.src_file = os.path.join(self.test_dir, "test_payload.bin")
        with open(self.src_file, "wb") as f:
            f.write(os.urandom(self.file_size))

        self.expected_hash = compute_file_sha256(self.src_file)
        self.port = 5020

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_direct_peer_transfer(self):
        receiver = TCPReceiver(host="127.0.0.1", port=self.port, save_dir=self.receiver_dir)
        recv_result = {}

        def run_receiver():
            nonlocal recv_result
            recv_result = receiver.listen_once(timeout=5.0)

        t_recv = threading.Thread(target=run_receiver)
        t_recv.start()
        time.sleep(0.3)  # Allow socket to bind

        sender = TCPSender(target_ip="127.0.0.1", target_port=self.port)
        progress_reports = []

        def on_prog(p):
            progress_reports.append(p)

        send_result = sender.send_file(
            filepath=self.src_file,
            transfer_id="T-TEST",
            pair_id="P-001",
            sender_name="ClientA",
            receiver_name="ClientB",
            progress_cb=on_prog
        )

        t_recv.join(timeout=5.0)

        # Verify Sender Results
        self.assertTrue(send_result["sha256_match"], "Sender reported integrity mismatch.")
        self.assertEqual(send_result["bytes_sent"], self.file_size)
        self.assertGreater(send_result["throughput_mbps"], 0.0)

        # Verify Receiver Results
        self.assertTrue(recv_result.get("sha256_match"), "Receiver reported integrity mismatch.")
        self.assertEqual(recv_result.get("bytes_received"), self.file_size)

        # Verify disk output
        saved_file = os.path.join(self.receiver_dir, "test_payload.bin")
        self.assertTrue(os.path.isfile(saved_file), "Received file was not saved on disk.")
        actual_hash = compute_file_sha256(saved_file)
        self.assertEqual(actual_hash, self.expected_hash, "File hash does not match original payload.")

        # Verify progress reports were triggered
        self.assertGreater(len(progress_reports), 0)


if __name__ == "__main__":
    unittest.main()
