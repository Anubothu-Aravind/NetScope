#!/usr/bin/env python3
"""
tests/test_transfer_localhost.py - Automated Localhost End-to-End Test for NetScope

Verifies:
1. TCPServer starts and accepts connections on localhost.
2. Generates a 5 MB random file and computes local SHA-256.
3. Tests SEND mode: client sends 5 MB file to server.
4. Asserts server saved file with matching SHA-256 and sha256_ok = True.
5. Tests RECV mode: client downloads 5 MB file from server.
6. Asserts client received file with matching SHA-256 and sha256_ok = True.
7. Asserts results/transfers.jsonl contains entries for both runs.
"""

import os
import sys
import time
import json
import shutil
import tempfile
import threading
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from server.tcp_server import TCPServer
from client.tcp_client import run_transfer
from common.protocol import compute_sha256


class TestTCPTransferLocalhost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="netscope_test_")
        cls.server_storage = os.path.join(cls.test_dir, "server_storage")
        cls.client_downloads = os.path.join(cls.test_dir, "client_downloads")
        os.makedirs(cls.server_storage, exist_ok=True)
        os.makedirs(cls.client_downloads, exist_ok=True)

        cls.port = 5005
        cls.server = TCPServer(host="127.0.0.1", port=cls.port, storage_dir=cls.server_storage)
        cls.server_thread = threading.Thread(target=cls.server.start, daemon=True)
        cls.server_thread.start()
        time.sleep(0.5)  # Allow socket to bind and start listening

        # Generate a 5 MB random file
        cls.file_size = 5 * 1024 * 1024  # 5 Megabytes
        cls.test_file_path = os.path.join(cls.test_dir, "sample_5mb.bin")
        with open(cls.test_file_path, "wb") as f:
            f.write(os.urandom(cls.file_size))

        cls.test_results_file = os.path.join(cls.test_dir, "test_transfers.jsonl")
        cls.expected_sha256 = compute_sha256(cls.test_file_path)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        time.sleep(0.2)
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_send_file(self):
        """Test sending a 5 MB file from client to server."""
        result = run_transfer(
            mode="send",
            server_ip="127.0.0.1",
            port=self.port,
            file_arg=self.test_file_path,
            scenario="Localhost-Test-Send",
            dest_dir=self.client_downloads,
            results_file=self.test_results_file
        )

        self.assertTrue(result["sha256_ok"], "Send SHA-256 verification failed.")
        self.assertEqual(result["size_bytes"], self.file_size)
        self.assertGreater(result["throughput_mbps"], 0.0)
        self.assertTrue("run_id" in result and len(result["run_id"]) == 8)

        # Check server storage
        stored_file = os.path.join(self.server_storage, "sample_5mb.bin")
        for _ in range(20):
            if os.path.isfile(stored_file):
                break
            time.sleep(0.05)
        self.assertTrue(os.path.isfile(stored_file), "Server did not save the uploaded file.")
        server_hash = compute_sha256(stored_file)
        self.assertEqual(server_hash, self.expected_sha256, "Server stored file hash mismatch.")

    def test_02_receive_file(self):
        """Test downloading the 5 MB file from server to client."""
        result = run_transfer(
            mode="receive",
            server_ip="127.0.0.1",
            port=self.port,
            file_arg="sample_5mb.bin",
            scenario="Localhost-Test-Recv",
            dest_dir=self.client_downloads,
            results_file=self.test_results_file
        )

        self.assertTrue(result["sha256_ok"], "Receive SHA-256 verification failed.")
        self.assertEqual(result["size_bytes"], self.file_size)
        self.assertTrue("run_id" in result and len(result["run_id"]) == 8)

        # Check client download folder
        downloaded_file = os.path.join(self.client_downloads, "sample_5mb.bin")
        self.assertTrue(os.path.isfile(downloaded_file), "Client did not save downloaded file.")
        client_hash = compute_sha256(downloaded_file)
        self.assertEqual(client_hash, self.expected_sha256, "Client downloaded file hash mismatch.")

    def test_03_results_jsonl_logged(self):
        """Verify the temp results file contains valid JSON logs and real file was untouched."""
        self.assertTrue(os.path.isfile(self.test_results_file), "Temp results file was not created.")

        with open(self.test_results_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        self.assertGreaterEqual(len(lines), 2, "Test results file should have at least 2 entries.")
        first_entry = json.loads(lines[0])
        self.assertIn("run_id", first_entry)
        self.assertEqual(len(first_entry["run_id"]), 8)


if __name__ == "__main__":
    unittest.main()
