#!/usr/bin/env python3
"""
tests/test_integrity.py - Unit Tests for Cryptographic Integrity Checks
"""

import unittest
import tempfile
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from client.integrity import compute_file_sha256, StreamHashValidator


class TestIntegrity(unittest.TestCase):
    def setUp(self):
        self.test_data = os.urandom(1024 * 1024)  # 1 MB
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.write(self.test_data)
        self.tmp.close()

    def tearDown(self):
        if os.path.isfile(self.tmp.name):
            os.remove(self.tmp.name)

    def test_file_hash(self):
        digest = compute_file_sha256(self.tmp.name)
        self.assertEqual(len(digest), 64)
        # Re-computing yields identical digest
        self.assertEqual(compute_file_sha256(self.tmp.name), digest)

    def test_stream_hash_validator(self):
        file_hash = compute_file_sha256(self.tmp.name)
        validator = StreamHashValidator(expected_hash=file_hash)

        # Feed in chunks
        chunk_size = 65536
        with open(self.tmp.name, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                validator.update(chunk)

        self.assertEqual(validator.digest(), file_hash)
        self.assertTrue(validator.verify())

    def test_tamper_detection(self):
        file_hash = compute_file_sha256(self.tmp.name)
        validator = StreamHashValidator(expected_hash=file_hash)

        # Corrupt one byte
        corrupted = bytearray(self.test_data)
        corrupted[100] = (corrupted[100] + 1) % 256
        validator.update(bytes(corrupted))

        self.assertNotEqual(validator.digest(), file_hash)
        self.assertFalse(validator.verify())


if __name__ == "__main__":
    unittest.main()
