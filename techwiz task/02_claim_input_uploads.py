"""
ASSUREX - STEP 2
Collect claim fault details + upload proof files.

Allowed documents: PDF/JPG/JPEG/PNG
Default max file size: 10 MB per file.

Run after Step 1:
    python 02_claim_input_uploads.py
"""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
SESSION_PATH = OUTPUT_DIR / "step01_session.json"
CLAIM_PATH = OUTPUT_DIR / "step02_claim.json"
CLAIMS_DIR = BASE_DIR / "data" / "claims"

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_FILE_SIZE = 10 * 1024 * 1024


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def copy_document(source: Path, destination_dir: Path) -> dict:
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"File not found: {source}")
    if source.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {source.suffix}. Use PDF/JPG/JPEG/PNG.")
    size = source.stat().st_size
    if size > MAX_FILE_SIZE:
        raise ValueError(f"File is larger than 10 MB: {source.name}")

    destination_dir.mkdir(parents=True, exist_ok=True)
    safe_name = source.name.replace(" ", "_")
    destination = destination_dir / safe_name
    shutil.copy2(source, destination)
    return {
        "filename": destination.name,
        "path": str(destination),
        "extension": destination.suffix.lower(),
        "size_bytes": size,
    }


def collect_document(label: str, required: bool, destination_dir: Path) -> dict | None:
    required_text = "required" if required else "optional"
    raw = input(f"Path for {label} ({required_text}; blank to skip): ").strip()
    if not raw:
        if required:
            raise ValueError(f"{label} is required for the claim.")
        return None
    return copy_document(Path(raw).expanduser(), destination_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="AssureX Step 2 - claim data and document upload")
    parser.add_argument("--session", default=str(SESSION_PATH))
    args = parser.parse_args()

    session_path = Path(args.session)
    if not session_path.exists():
        raise SystemExit("Run Step 1 first so the selected product/session exists.")

    session = json.loads(session_path.read_text(encoding="utf-8"))
    claim_id = "CLM-" + secrets.token_hex(6).upper()
    claim_dir = CLAIMS_DIR / claim_id

    print("=" * 68)
    print("ASSUREX - STEP 2: CLAIM DETAILS & FILE UPLOAD")
    print("=" * 68)

    claim = {
        "claim_id": claim_id,
        "user_id": session["user_id"],
        "role": session["role"],
        "product": session["selected_product"],
        "fault_date": ask("Fault occurrence date", date.today().isoformat()),
        "fault_description": ask("What went wrong", "Screen has vertical lines"),
        "fault_category": ask("Fault category", "Screen / Display Defect"),
        "damage_type": ask("Damage type", "Manufacturing / Functional defect"),
        "previous_repair": ask("Was the product repaired before? (yes/no)", "no").lower() == "yes",
        "previous_replacement": ask("Was the product replaced before? (yes/no)", "no").lower() == "yes",
        "unauthorized_repair": ask("Was any previous repair done by an unauthorized center? (yes/no)", "no").lower() == "yes",
        "repair_center": ask("Previous repair center (blank when none)", ""),
        "claim_submission_date": ask("Claim submission date", date.today().isoformat()),
    }

    documents: dict[str, dict | None] = {}
    documents["purchase_receipt"] = collect_document("purchase receipt / invoice", True, claim_dir)
    documents["warranty_card"] = collect_document("warranty card", True, claim_dir)
    documents["product_image"] = collect_document("product image", True, claim_dir)
    documents["serial_number_evidence"] = collect_document("serial-number evidence photo", True, claim_dir)
    documents["fault_evidence"] = collect_document("fault / damage evidence", True, claim_dir)
    documents["repair_report"] = collect_document("repair report", False, claim_dir)

    claim["documents"] = documents
    claim["missing_documents"] = [name for name, info in documents.items() if info is None]
    claim["status"] = "Draft"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CLAIM_PATH.write_text(json.dumps(claim, indent=2), encoding="utf-8")
    print(f"\nClaim created: {claim_id}")
    print(f"Saved to: {CLAIM_PATH}")


if __name__ == "__main__":
    main()
