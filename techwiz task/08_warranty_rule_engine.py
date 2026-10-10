"""
ASSUREX - STEP 8
Configurable warranty rule engine.

Rules are loaded from policies/*.json. Nothing important is hard-coded into
this script, so different product categories can have different policies.

Run:
    python 08_warranty_rule_engine.py --claim outputs/step05_verified_claim.json
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
POLICY_DIR = BASE_DIR / "policies"
OUTPUT_DIR = BASE_DIR / "outputs"
DEFAULT_CLAIM = OUTPUT_DIR / "step05_verified_claim.json"
OUT_PATH = OUTPUT_DIR / "step08_warranty_result.json"


def to_date(value: str | None):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def load_policy(category: str) -> dict:
    name_map = {
        "laptop": "laptop_policy.json",
        "smartphone": "smartphone_policy.json",
        "tv": "tv_policy.json",
        "television": "tv_policy.json",
        "refrigerator": "refrigerator_policy.json",
        "ac": "ac_policy.json",
        "air conditioner": "ac_policy.json",
        "microwave": "microwave_policy.json",
        "washing machine": "washing_machine_policy.json",
        "printer": "printer_policy.json",
    }
    file_name = name_map.get(category.strip().lower())
    if not file_name:
        raise ValueError(f"No policy file configured for category: {category}")
    path = POLICY_DIR / file_name
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_rules(claim: dict, policy: dict) -> dict:
    product = claim.get("product", {})
    verified = claim.get("verified_receipt_data", {})
    docs = claim.get("documents", {})

    passed, warnings, failures, review_flags = [], [], [], []

    purchase = to_date(verified.get("purchase_date") or product.get("purchase_date"))
    claim_date = to_date(claim.get("claim_submission_date"))
    fault_date = to_date(claim.get("fault_date"))

    try:
        warranty_months = int(verified.get("warranty_months") or product.get("warranty_months") or 0)
    except (ValueError, TypeError):
        warranty_months = 0
    if not purchase or not claim_date or not fault_date:
        review_flags.append("Purchase, fault, or submission date is missing or invalid")
    if not warranty_months:
        review_flags.append("Warranty duration is missing")
    expiry = None
    if purchase:
        # Month arithmetic is simpler to keep dependency-free for the demo.
        import calendar
        month = purchase.month - 1 + warranty_months
        year = purchase.year + month // 12
        month = month % 12 + 1
        day = min(purchase.day, calendar.monthrange(year, month)[1])
        expiry = date(year, month, day)
    explicit_expiry = to_date(product.get("warranty_expiry_date") or verified.get("warranty_expiry"))
    if explicit_expiry:
        expiry = explicit_expiry
    if product.get("is_extended") or verified.get("extended_warranty"):
        extended_expiry = to_date(product.get("extended_warranty_expiry"))
        if extended_expiry and (expiry is None or extended_expiry > expiry):
            expiry = extended_expiry

    if expiry and claim_date:
        remaining = (expiry - claim_date).days
        if remaining < 0:
            failures.append("Warranty expired")
        elif remaining <= policy.get("nearing_expiry_days", 30):
            warnings.append(f"Warranty nearing expiry ({remaining} days remaining)")
        else:
            passed.append(f"Warranty active ({remaining} days remaining)")

    if not docs.get("purchase_receipt"):
        failures.append("Purchase proof missing")
    else:
        passed.append("Purchase proof present")

    serial_receipt = str(verified.get("serial_number") or "").strip().lower()
    serial_product = str(product.get("serial_number") or "").strip().lower()
    if serial_receipt and serial_product:
        if serial_receipt == serial_product:
            passed.append("Serial number matches product record")
        else:
            review_flags.append("Serial number mismatch")

    damage = str(claim.get("damage_type", "")).strip().lower()
    for excluded in policy.get("excluded_damage", []):
        if excluded.lower() in damage:
            failures.append(f"Excluded damage: {excluded}")

    repair_center = str(claim.get("repair_center", "")).strip()
    unauthorized = bool(claim.get("unauthorized_repair", False))
    authorized_centers = {str(x).lower() for x in policy.get("authorized_service_centers", [])}
    if claim.get("previous_repair"):
        if unauthorized:
            failures.append("Unauthorized repair detected")
        elif repair_center and repair_center.lower() in authorized_centers:
            passed.append("Previous repair was at an authorized center")
        elif repair_center:
            review_flags.append("Previous repair center could not be verified")

    covered_faults = [str(x).lower() for x in policy.get("covered_fault_categories", [])]
    fault_category = str(claim.get("fault_category", "")).lower()
    if covered_faults and not any(item in fault_category for item in covered_faults):
        review_flags.append("Fault category is not clearly listed as covered")
    else:
        passed.append("Fault category is covered")

    if purchase and fault_date and fault_date < purchase:
        review_flags.append("Fault date is before purchase date")
    if fault_date and claim_date and fault_date > claim_date:
        review_flags.append("Fault date is after claim submission date")

    reporting_period = policy.get("claim_reporting_period_days")
    if reporting_period is None:
        reporting_period = policy.get("reporting_period", {}).get("days")
    if reporting_period is not None and fault_date and claim_date:
        days_to_report = (claim_date - fault_date).days
        if days_to_report > int(reporting_period):
            warnings.append(f"Claim was reported {days_to_report} days after the fault; policy period is {int(reporting_period)} days")
            review_flags.append("Claim reported outside the policy reporting period")

    if claim.get("previous_replacement"):
        review_flags.append("Previous product replacement requires reviewer verification")

    for repair in claim.get("repair_records", []):
        repair_date = to_date(repair.get("repair_date"))
        if purchase and repair_date and repair_date < purchase:
            review_flags.append("Repair date is before purchase date")
        if not repair.get("authorized"):
            review_flags.append("A repair has no verified authorized-service status")

    missing_documents = [name for name, info in docs.items() if not info]
    required_documents = set(policy.get("mandatory_documents", []))
    missing_required = sorted(name for name in required_documents if not docs.get(name))
    if missing_required:
        review_flags.append("Missing mandatory documents: " + ", ".join(missing_required))
    elif required_documents:
        passed.append("Mandatory documents present")

    if claim.get("document_duplicate_found"):
        review_flags.append("Duplicate document indicator")
    if claim.get("duplicate_claim_flags"):
        review_flags.extend(str(flag) for flag in claim["duplicate_claim_flags"])
    if claim.get("extracted_fields", {}).get("_serial_mismatch_warning"):
        review_flags.append("Receipt and warranty-card serial numbers differ")
    warranty_product = str(claim.get("warranty_ocr_fields", {}).get("product_name") or "").lower()
    product_model = str(product.get("model") or "").lower().strip()
    if warranty_product and product_model and product_model not in warranty_product:
        review_flags.append("Warranty-card product/model differs from the registered product")

    result = {
        "claim_id": claim["claim_id"],
        "policy": policy["policy_name"],
        "warranty_expiry": expiry.isoformat() if expiry else None,
        "days_remaining": (expiry - claim_date).days if expiry and claim_date else None,
        "warranty_status": ("expired" if expiry and claim_date and expiry < claim_date else
                            "near_expiry" if expiry and claim_date and (expiry - claim_date).days <= policy.get("nearing_expiry_days", 30) else
                            "active" if expiry and claim_date else "unknown"),
        "days_to_report": (claim_date - fault_date).days if claim_date and fault_date else None,
        "passed_rules": passed,
        "warnings": warnings,
        "hard_failures": failures,
        "manual_review_flags": review_flags,
        "missing_documents": missing_required,
        "rule_status": "FAIL" if failures else ("MANUAL_REVIEW" if review_flags else "PASS"),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="AssureX Step 8 - warranty rule engine")
    parser.add_argument("--claim", default=str(DEFAULT_CLAIM))
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    claim = json.loads(Path(args.claim).read_text(encoding="utf-8"))
    category = claim["product"].get("category", "Laptop")
    policy = load_policy(category)
    result = evaluate_rules(claim, policy)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nSaved to: {args.out}")


if __name__ == "__main__":
    main()
