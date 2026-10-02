"""
client/integrity.py - SHA-256 Cryptographic Integrity Helper for NetScope Transfers
"""

import hashlib
import os
from typing import Tuple


def compute_file_sha256(filepath: str, chunk_size: int = 65536) -> str:
    """Compute the hexadecimal SHA-256 digest of a local file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


class StreamHashValidator:
    """Incrementally computes SHA-256 as network chunks are streamed."""
    def __init__(self, expected_hash: str = ""):
        self.hasher = hashlib.sha256()
        self.expected_hash = expected_hash.lower()
        self.bytes_hashed = 0

    def update(self, chunk: bytes):
        self.hasher.update(chunk)
        self.bytes_hashed += len(chunk)

    def digest(self) -> str:
        return self.hasher.hexdigest()

    def verify(self) -> bool:
        if not self.expected_hash:
            return True
        return self.hasher.hexdigest().lower() == self.expected_hash
