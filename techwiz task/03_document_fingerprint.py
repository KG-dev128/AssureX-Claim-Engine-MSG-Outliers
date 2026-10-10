"""
ASSUREX - STEP 3
SHA-256 document fingerprinting + duplicate document detection.

The system hashes the actual uploaded file bytes. If the same bytes were used
before, the registry reports a duplicate/reuse warning.

Run:
    python 03_document_fingerprint.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
DEFAULT_CLAIM = OUTPUT_DIR / "step02_claim.json"
REGISTRY_PATH = BASE_DIR / "data" / "document_hash_registry.json"
OUT_PATH = OUTPUT_DIR / "step03_fingerprints.json"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        while chunk := file_handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(registry: dict) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="AssureX Step 3 - document SHA-256 fingerprinting")
    parser.add_argument("--claim", default=str(DEFAULT_CLAIM))
    args = parser.parse_args()

    claim_path = Path(args.claim)
    if not claim_path.exists():
        raise SystemExit("Run Step 2 first. Claim JSON was not found.")

    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    registry = load_registry()
    fingerprints = []
    duplicate_flags = []

    for document_type, info in claim.get("documents", {}).items():
        if not info:
            continue
        path = Path(info["path"])
        if not path.exists():
            duplicate_flags.append(f"Missing file on disk: {document_type}")
            continue

        digest = sha256_file(path)
        old_record = registry.get(digest)
        current_record = {
            "claim_id": claim["claim_id"],
            "document_type": document_type,
            "filename": path.name,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

        is_duplicate = old_record is not None and old_record["claim_id"] != claim["claim_id"]
        if is_duplicate:
            duplicate_flags.append(
                f"Duplicate document: {document_type} matches Claim {old_record['claim_id']} / {old_record['filename']}"
            )
        elif old_record is None:
            registry[digest] = current_record

        fingerprints.append(
            {
                "document_type": document_type,
                "filename": path.name,
                "sha256": digest,
                "duplicate": is_duplicate,
                "previous_use": old_record,
            }
        )

    result = {
        "claim_id": claim["claim_id"],
        "fingerprints": fingerprints,
        "duplicate_flags": duplicate_flags,
        "document_duplicate_found": bool(duplicate_flags),
    }

    claim["document_fingerprints"] = fingerprints
    claim["duplicate_flags"] = duplicate_flags
    claim["document_duplicate_found"] = bool(duplicate_flags)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    claim_path.write_text(json.dumps(claim, indent=2), encoding="utf-8")
    save_registry(registry)

    print("SHA-256 fingerprinting complete.")
    for item in fingerprints:
        print(f"  {item['document_type']}: {item['sha256']}")
    if duplicate_flags:
        print("\nWARNING - duplicate/reuse flag detected:")
        for flag in duplicate_flags:
            print(f"  - {flag}")
    print(f"\nSaved to: {OUT_PATH}")


if __name__ == "__main__":
    main()
