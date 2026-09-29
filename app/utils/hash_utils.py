"""
app/utils/hash_utils.py
Cryptographic hash utilities for document integrity & deduplication (FR xxxi).
Computes SHA-256 digests.
"""
import hashlib
import os


def compute_sha256(file_path: str) -> str:
    """Compute SHA-256 checksum of a file on disk."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def compute_bytes_sha256(file_bytes: bytes) -> str:
    """Compute SHA-256 checksum directly from memory bytes."""
    return hashlib.sha256(file_bytes).hexdigest()
