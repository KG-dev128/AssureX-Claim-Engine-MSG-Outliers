"""
ASSUREX - STEP 7
Arbiter: compare Python ML vs Teachable Machine.

Input format for TM JSON:
{
  "prediction": "Valid Claim",
  "top_class": "Valid Claim",
  "confidence": 0.84,
  "confidences": {
    "Valid Claim": 0.84,
    "Invalid Claim": 0.05,
    "Manual Review": 0.11
  }
}

For a batch of >=30 unseen test claims, prepare one row per claim or use the
same logic repeatedly from your web application.

Run for one claim:
    python 07_compare_models.py --python outputs/step06_python_prediction.json --tm tm_prediction.json
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_THRESHOLDS = {
    "strong_match_max_difference": 0.15,
    "acceptable_match_max_difference": 0.30,
    "low_confidence_below": 0.60,
}


def load_thresholds(path: Path | None = None) -> dict:
    path = path or BASE_DIR / "policies" / "model_comparison.json"
    config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    thresholds = {**DEFAULT_THRESHOLDS, **config}
    for key in DEFAULT_THRESHOLDS:
        value = float(thresholds[key])
        if not 0 <= value <= 1:
            raise ValueError(f"Comparison threshold {key} must be between 0 and 1.")
        thresholds[key] = value
    return thresholds

CLASS_NAMES = ["Valid Claim", "Invalid Claim", "Manual Review"]
STRONG_MATCH_LIMIT = 0.15
ACCEPTABLE_MATCH_LIMIT = 0.30
LOW_CONFIDENCE_LIMIT = 0.60


def compare_one(python_data: dict, tm_data: dict, thresholds: dict | None = None) -> dict:
    thresholds = load_thresholds() if thresholds is None else {**DEFAULT_THRESHOLDS, **thresholds}
    py_scores = python_data["python"]["confidences"] if "python" in python_data else python_data["confidences"]
    tm_scores = tm_data["confidences"]

    py_top = max(py_scores, key=py_scores.get)
    tm_top = max(tm_scores, key=tm_scores.get)
    py_conf = float(py_scores[py_top])
    tm_conf = float(tm_scores[tm_top])
    difference = abs(py_conf - tm_conf)
    predictions_match = py_top == tm_top

    if not predictions_match:
        status = "Model Disagreement"
    elif min(py_conf, tm_conf) < thresholds["low_confidence_below"]:
        status = "Uncertain Result"
    elif difference < thresholds["strong_match_max_difference"]:
        status = "Strong Match"
    elif difference < thresholds["acceptable_match_max_difference"]:
        status = "Acceptable Match"
    else:
        status = "Weak Match"

    manual_review = status in {"Model Disagreement", "Uncertain Result", "Weak Match"}

    return {
        "claim_id": python_data.get("claim_id"),
        "python_prediction": py_top,
        "python_confidences": py_scores,
        "tm_prediction": tm_top,
        "tm_confidences": tm_scores,
        "prediction_match": predictions_match,
        "python_top_confidence": py_conf,
        "tm_top_confidence": tm_conf,
        "confidence_difference": difference,
        "consistency_status": status,
        "manual_review_trigger": manual_review,
        "explanation": (
            f"Python={py_top} ({py_conf:.1%}), TM={tm_top} ({tm_conf:.1%}), "
            f"top-class difference={difference:.1%}, status={status}."
        ),
    }



def compare_batch(rows: list[dict]) -> list[dict]:
    results = []
    for row in rows:
        py = {
            "claim_id": row.get("Claim_ID") or row.get("claim_id"),
            "python": {
                "confidences": {
                    "Valid Claim": float(row["Python_Valid_Confidence"]),
                    "Invalid Claim": float(row["Python_Invalid_Confidence"]),
                    "Manual Review": float(row["Python_Manual_Review_Confidence"]),
                }
            }
        }
        tm = {
            "confidences": {
                "Valid Claim": float(row["TM_Valid_Confidence"]),
                "Invalid Claim": float(row["TM_Invalid_Confidence"]),
                "Manual Review": float(row["TM_Manual_Review_Confidence"]),
            }
        }
        result = compare_one(py, tm)
        result["actual_class"] = row.get("Actual_Class", "")
        result["card_filename"] = row.get("Card_Filename", "")
        result["warranty_result"] = row.get("Warranty_Result", "")
        result["missing_documents"] = row.get("Missing_Documents", "")
        result["contradictions"] = row.get("Contradictions", "")
        result["duplicate_indicator"] = row.get("Duplicate_Indicator", "")
        results.append(result)
    return results

def main() -> None:
    parser = argparse.ArgumentParser(description="AssureX Step 7 - model comparison")
    parser.add_argument("--python", help="Step 6 Python prediction JSON for one claim")
    parser.add_argument("--tm", help="Teachable Machine confidence JSON for one claim")
    parser.add_argument("--batch", help="CSV with 30+ unseen test claims")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "outputs" / "step07_comparison.json"))
    args = parser.parse_args()

    if args.batch:
        with Path(args.batch).open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) < 30:
            raise SystemExit(f"The formal comparison requires at least 30 unseen claims; found {len(rows)}.")
        results = compare_batch(rows)
        output_path = Path(args.out).with_suffix(".csv")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(results[0].keys())
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"Compared {len(results)} unseen claims.")
        print(f"Saved batch report: {output_path}")
        return

    if not args.python or not args.tm:
        raise SystemExit("Provide --python and --tm for one claim, or --batch for the 30+ claim report.")

    python_data = json.loads(Path(args.python).read_text(encoding="utf-8"))
    tm_data = json.loads(Path(args.tm).read_text(encoding="utf-8"))

    result = compare_one(python_data, tm_data)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(json.dumps(result, indent=2))
    print(f"\nSaved to: {args.out}")


if __name__ == "__main__":
    main()
