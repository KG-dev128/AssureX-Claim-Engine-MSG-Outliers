"""
ASSUREX - STEP 9
Final Master Decision.

Combines:
- Python prediction + all 3 Python confidences
- Teachable Machine prediction + all 3 TM confidences
- model consistency status
- warranty rule result
- missing documents
- contradictions
- duplicate indicators

Final automated recommendation:
    Likely Valid
    Likely Invalid
    Manual Review Required
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUT_PATH = OUTPUT_DIR / "step09_final_decision.json"


def unique_reasons(items):
    return list(dict.fromkeys(str(x) for x in items if str(x).strip()))


def main() -> None:
    parser = argparse.ArgumentParser(description="AssureX Step 9 - final decision")
    parser.add_argument("--python", required=True)
    parser.add_argument("--comparison", required=True)
    parser.add_argument("--warranty", required=True)
    parser.add_argument("--claim", required=True)
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    py = json.loads(Path(args.python).read_text(encoding="utf-8"))
    comparison = json.loads(Path(args.comparison).read_text(encoding="utf-8"))
    warranty = json.loads(Path(args.warranty).read_text(encoding="utf-8"))
    claim = json.loads(Path(args.claim).read_text(encoding="utf-8"))

    manual_reasons = []

    if comparison.get("manual_review_trigger"):
        manual_reasons.append(
            comparison.get("consistency_status", "Model consistency issue")
        )

    manual_reasons.extend(warranty.get("manual_review_flags", []))

    missing_documents = claim.get("missing_documents", [])
    if missing_documents:
        manual_reasons.append(
            "Missing documents: " + ", ".join(missing_documents)
        )

    if claim.get("document_duplicate_found"):
        manual_reasons.append("Duplicate document flag")

    hard_failures = warranty.get("hard_failures", [])
    py_class = comparison.get("python_prediction")
    tm_class = comparison.get("tm_prediction")

    # Manual-review triggers take precedence over an automatic decision.
    if manual_reasons:
        decision = "Manual Review Required"
    elif hard_failures:
        decision = "Likely Invalid"
    elif py_class == "Invalid Claim" and tm_class == "Invalid Claim":
        decision = "Likely Invalid"
    elif (
        py_class == "Valid Claim"
        and tm_class == "Valid Claim"
        and warranty.get("rule_status") == "PASS"
    ):
        decision = "Likely Valid"
    else:
        decision = "Manual Review Required"

    explanation_parts = [
        f"Python model: {py_class}",
        f"Teachable Machine: {tm_class}",
        f"Model consistency: {comparison.get('consistency_status')}",
        f"Confidence difference: {float(comparison.get('confidence_difference', 0)):.2%}",
        f"Warranty rules: {warranty.get('rule_status')}",
    ]

    if hard_failures:
        explanation_parts.append(
            "Hard failures: " + "; ".join(hard_failures)
        )

    if manual_reasons:
        explanation_parts.append(
            "Manual-review reasons: " + "; ".join(unique_reasons(manual_reasons))
        )

    python_payload = py.get("python", py)
    py_confidences = python_payload.get("confidences", {})
    tm_confidences = comparison.get("tm_confidences", {})

    result = {
        "claim_id": claim["claim_id"],
        "decision": decision,
        "explanation": " | ".join(explanation_parts),
        "manual_review_required": decision == "Manual Review Required",

        # Complete AI evidence is preserved for reviewer/audit use.
        "ai_results": {
            "python": {
                "prediction": py_class,
                "confidences": py_confidences,
                "model_version": python_payload.get("model_version"),
            },
            "teachable_machine": {
                "prediction": tm_class,
                "confidences": tm_confidences,
                "model": comparison.get(
                    "tm_model", "Google Teachable Machine"
                ),
            },
            "comparison": {
                "prediction_match": comparison.get("prediction_match"),
                "consistency_status": comparison.get("consistency_status"),
                "confidence_difference": comparison.get(
                    "confidence_difference"
                ),
            },
        },

        "supporting_factors": warranty.get("passed_rules", []),
        "opposing_factors": hard_failures,
        "warning_factors": warranty.get("warnings", []),
        "manual_review_reasons": unique_reasons(manual_reasons),
        "source_outputs": {
            "python": str(Path(args.python)),
            "comparison": str(Path(args.comparison)),
            "warranty": str(Path(args.warranty)),
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, indent=2, default=str),
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2))
    print(f"\nSaved to: {out}")


if __name__ == "__main__":
    main()
