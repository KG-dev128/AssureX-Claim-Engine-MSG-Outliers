"""
ASSUREX - STEP 5
Human-in-the-loop OCR verification.

The script displays the OCR fields and lets the user correct them before the
claim is sent to the AI paths.

Run:
    python 05_ocr_verification.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
OCR_PATH = OUTPUT_DIR / "step04_ocr.json"
CLAIM_PATH = OUTPUT_DIR / "step02_claim.json"
OUT_PATH = OUTPUT_DIR / "step05_verified_claim.json"


def ask(prompt: str, default):
    value = input(f"{prompt} [{default if default is not None else 'blank'}]: ").strip()
    return value if value else default


def main() -> None:
    parser = argparse.ArgumentParser(description="AssureX Step 5 - OCR verification")
    parser.add_argument("--ocr", default=str(OCR_PATH))
    parser.add_argument("--claim", default=str(CLAIM_PATH))
    args = parser.parse_args()

    ocr = json.loads(Path(args.ocr).read_text(encoding="utf-8"))
    claim = json.loads(Path(args.claim).read_text(encoding="utf-8"))
    extracted = ocr.get("extracted_fields", {})

    print("=" * 68)
    print("ASSUREX - STEP 5: OCR VERIFICATION")
    print("=" * 68)
    print("The OCR values are shown below. Press Enter to keep a value unchanged.\n")

    verified = {
        "purchase_date": ask("Purchase date", extracted.get("purchase_date")),
        "invoice_number": ask("Invoice number", extracted.get("invoice_number")),
        "serial_number": ask("Serial number", extracted.get("serial_number")),
        "amount_paid": ask("Amount paid", extracted.get("amount_paid")),
        "warranty_months": ask("Warranty duration in months", extracted.get("warranty_months")),
        "retailer": ask("Retailer", extracted.get("retailer_guess")),
    }

    # Store what was OCR-generated and what the human confirmed separately.
    claim["ocr_extracted"] = extracted
    claim["verified_receipt_data"] = verified
    claim["verification_status"] = "human_confirmed"

    # Update the product serial from the verified receipt when available.
    if verified.get("serial_number"):
        claim["receipt_serial_number"] = verified["serial_number"]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    Path(OUT_PATH).write_text(json.dumps(claim, indent=2), encoding="utf-8")

    print("\nVerification saved. Click flow concept: Confirm & Evaluate")
    print(f"Output: {OUT_PATH}")


if __name__ == "__main__":
    main()
