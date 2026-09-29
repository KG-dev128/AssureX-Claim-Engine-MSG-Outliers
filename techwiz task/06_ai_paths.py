"""
ASSUREX - STEP 6
Corrected Python ML inference + 800x600 Claim Summary Card.

This version matches the supplied leakage-corrected notebook:
- Uses the saved corrected sklearn pipeline.
- Uses the separate LabelEncoder saved by the notebook.
- Recreates the same prediction-time features used during training.
- Does NOT use outcome/assessment fields such as Scenario_Type, Risk_Level,
  Warranty_Status, Fault_Coverage, Match/Contradiction indicators, etc.
- Generates exactly one 800x600 Summary Card with no AI prediction,
  confidence score, or final decision on the card.

Expected model artifacts from the uploaded corrected notebook:
    best_corrected_assurex_model.joblib
    corrected_label_encoder.joblib

Example:
    python 06_ai_paths.py ^
      --claim outputs/step05_verified_claim.json ^
      --model models/best_corrected_assurex_model.joblib ^
      --encoder models/corrected_label_encoder.joblib
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
DEFAULT_CLAIM = OUTPUT_DIR / "step05_verified_claim.json"
DEFAULT_CARD = OUTPUT_DIR / "claim_summary_card_800x600.png"
DEFAULT_PREDICTION = OUTPUT_DIR / "step06_python_prediction.json"

CLASS_NAMES = ["Valid Claim", "Invalid Claim", "Manual Review"]

# These are the exact columns retained by the supplied corrected notebook
# after dropping identifiers, text, outcome/assessment fields, and raw dates.
TRAINING_FEATURES = [
    "Product_Category",
    "Brand",
    "Model_Number",
    "Purchase_Price",
    "Retailer",
    "Warranty_Duration_Months",
    "Product_Age_Months",
    "Fault_Type",
    "Damage_Type",
    "Purchase_Proof",
    "Warranty_Card",
    "Product_Image",
    "Serial_Number_Evidence",
    "Fault_Evidence",
    "Repair_Report",
    "Previous_Repair_Count",
    "Repair_Center",
    "Replaced_Parts",
    "Purchase_Year",
    "Purchase_Month",
    "Claim_Year",
    "Claim_Month",
    "Fault_Year",
    "Fault_Month",
    "Warranty_Years",
]


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"yes", "true", "1", "y"}


def parse_date(value):
    if value in (None, "", "nan"):
        return pd.NaT
    return pd.to_datetime(value, errors="coerce")


def document_status(documents: dict, key: str) -> str:
    return "Available" if documents.get(key) else "Missing"


def build_corrected_model_input(claim: dict, expected_features=None) -> pd.DataFrame:
    """
    Recreate the feature engineering in the supplied corrected notebook.

    IMPORTANT:
    Do not add target/outcome fields here. The whole point of the corrected
    notebook is to prevent the model from receiving fields that effectively
    reveal the answer.
    """
    product = claim.get("product", {})
    verified = claim.get("verified_receipt_data", {})
    docs = claim.get("documents", {})

    purchase_date = parse_date(
        verified.get("purchase_date") or product.get("purchase_date")
    )
    warranty_start_date = parse_date(
        product.get("warranty_start_date") or product.get("purchase_date")
    )
    claim_date = parse_date(claim.get("claim_submission_date"))
    fault_date = parse_date(claim.get("fault_date"))

    warranty_months_raw = (
        verified.get("warranty_months")
        or product.get("warranty_months")
        or 0
    )

    try:
        warranty_months = int(float(warranty_months_raw))
    except (TypeError, ValueError):
        warranty_months = 0

    # Product age is already collected by the app when available; otherwise
    # calculate it from the same prediction-time dates.
    product_age_months = product.get("product_age_months")
    if product_age_months in (None, "") and not pd.isna(purchase_date) and not pd.isna(claim_date):
        product_age_months = round((claim_date - purchase_date).days / 30.44, 2)
    else:
        try:
            product_age_months = float(product_age_months or 0)
        except (TypeError, ValueError):
            product_age_months = 0.0

    row = {
        "Product_Category": product.get("category", "Unknown"),
        "Brand": product.get("brand", "Unknown"),
        "Model_Number": product.get("model", "Unknown"),
        "Purchase_Price": float(product.get("purchase_price") or verified.get("amount_paid") or 0),
        "Retailer": verified.get("retailer") or product.get("retailer", "Unknown"),
        "Warranty_Duration_Months": warranty_months,
        "Product_Age_Months": product_age_months,
        "Fault_Type": claim.get("fault_type") or claim.get("fault_category", "Unknown"),
        "Damage_Type": claim.get("damage_type", "Unknown"),

        "Purchase_Proof": document_status(docs, "purchase_receipt"),
        "Warranty_Card": document_status(docs, "warranty_card"),
        "Product_Image": document_status(docs, "product_image"),
        "Serial_Number_Evidence": document_status(docs, "serial_number_evidence"),
        "Fault_Evidence": document_status(docs, "fault_evidence"),
        "Repair_Report": document_status(docs, "repair_report"),

        "Previous_Repair_Count": (
            int(claim.get("previous_repair_count", 0))
            if str(claim.get("previous_repair_count", "")).strip() not in {"", "None"}
            else int(as_bool(claim.get("previous_repair", False)))
        ),

        # These fields are retained by the corrected notebook, so inference
        # supplies the same kind of intake information. Blank values are safe
        # because the fitted preprocessing pipeline imputes missing values.
        "Repair_Center": claim.get("repair_center") or np.nan,
        "Replaced_Parts": claim.get("replaced_parts") or np.nan,

        "Purchase_Year": purchase_date.year if not pd.isna(purchase_date) else np.nan,
        "Purchase_Month": purchase_date.month if not pd.isna(purchase_date) else np.nan,
        "Claim_Year": claim_date.year if not pd.isna(claim_date) else np.nan,
        "Claim_Month": claim_date.month if not pd.isna(claim_date) else np.nan,
        "Fault_Year": fault_date.year if not pd.isna(fault_date) else np.nan,
        "Fault_Month": fault_date.month if not pd.isna(fault_date) else np.nan,
        "Warranty_Years": warranty_months / 12 if warranty_months else 0.0,
    }

    # The bundled binary uses date-column suffixes, unlike the accompanying
    # notebook. Derive those fields from source dates, then select the exact
    # fitted schema. Never invent defaults for unknown dates.
    dates = {
        "Purchase_Date": purchase_date,
        "Warranty_Start_Date": warranty_start_date,
        "Warranty_Expiry_Date": parse_date(product.get("warranty_expiry_date")),
        "Claim_Submission_Date": claim_date,
        "Fault_Occurrence_Date": fault_date,
        "Last_Repair_Date": parse_date(claim.get("last_repair_date")),
    }
    if pd.isna(dates["Warranty_Expiry_Date"]) and pd.notna(warranty_start_date) and warranty_months:
        dates["Warranty_Expiry_Date"] = warranty_start_date + pd.DateOffset(months=warranty_months)
    for name, value in dates.items():
        row[name + "_year"] = value.year if pd.notna(value) else np.nan
        row[name + "_month"] = value.month if pd.notna(value) else np.nan
    columns = list(expected_features) if expected_features is not None else TRAINING_FEATURES
    unsupported = set(columns) - set(row)
    if unsupported:
        raise ValueError(f"Unsupported saved model features: {sorted(unsupported)}")
    frame = pd.DataFrame([row], columns=columns)
    return frame


def load_label_encoder(path: Path):
    import joblib

    if not path.exists():
        raise FileNotFoundError(
            f"Label encoder not found: {path}\n"
            "Run the supplied corrected ML notebook and place "
            "corrected_label_encoder.joblib beside your model."
        )

    encoder = joblib.load(path)
    classes = [str(x) for x in encoder.classes_]

    missing = [name for name in CLASS_NAMES if name not in classes]
    if missing:
        raise ValueError(
            f"Encoder classes do not match AssureX classes. "
            f"Missing: {missing}; found: {classes}"
        )
    return encoder


def run_python_model(model_path: Path, encoder_path: Path, claim: dict) -> dict:
    import joblib

    if not model_path.exists():
        raise FileNotFoundError(
            f"Corrected Python model not found: {model_path}"
        )

    model = joblib.load(model_path)
    encoder = load_label_encoder(encoder_path)

    X = build_corrected_model_input(claim, getattr(model, "feature_names_in_", None))

    # The supplied notebook encodes y with LabelEncoder before fitting.
    predicted_encoded = int(np.asarray(model.predict(X)).reshape(-1)[0])
    probabilities = np.asarray(model.predict_proba(X)[0], dtype=float)
    if not np.isfinite(probabilities).all() or (probabilities < 0).any() or (probabilities > 1).any() or not np.isclose(probabilities.sum(), 1, atol=0.01):
        raise ValueError("Model returned invalid probabilities")

    encoded_classes = list(getattr(model, "classes_", range(len(probabilities))))
    decoded_classes = encoder.inverse_transform(
        np.asarray(encoded_classes, dtype=int)
    ).tolist()

    scores = {name: 0.0 for name in CLASS_NAMES}
    for class_name, probability in zip(decoded_classes, probabilities):
        if class_name in scores:
            scores[class_name] = float(probability)

    top_class = max(scores, key=scores.get)

    return {
        "model_version": "best_corrected_assurex_model",
        "model_file": model_path.name,
        "prediction_encoded": predicted_encoded,
        "prediction": top_class,
        "top_class": top_class,
        "confidence": scores[top_class],
        "confidences": {name: scores[name] for name in CLASS_NAMES},
        "model_input": X.astype(object).where(pd.notna(X), None).to_dict(orient="records")[0],
    }


def generate_summary_card(claim: dict, output_path: Path) -> None:
    """
    Standardized 800x600 image for the independent TM model.

    CRITICAL: no Python prediction, confidence, or final claim decision
    appears anywhere on this image.
    """
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(image)

    def font(size: int, bold: bool = False):
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        ]
        for candidate in candidates:
            p = Path(candidate)
            if p.exists():
                return ImageFont.truetype(str(p), size)
        return ImageFont.load_default()

    title_font = font(28, True)
    label_font = font(15, True)
    value_font = font(15, False)
    small_font = font(12, False)

    product = claim.get("product", {})
    verified = claim.get("verified_receipt_data", {})
    docs = claim.get("documents", {})
    model_input = build_corrected_model_input(claim).iloc[0]

    draw.rounded_rectangle(
        (18, 18, 782, 582), radius=14,
        outline="#1f2937", width=2, fill="white"
    )
    draw.text((38, 32), "ASSUREX - CLAIM SUMMARY", fill="#111827", font=title_font)
    draw.text(
        (38, 70),
        f"Claim ID: {claim.get('claim_id', 'N/A')}",
        fill="#4b5563", font=small_font
    )

    rows = [
        ("Product", f"{product.get('brand', '')} {product.get('model', '')}".strip() or "Unknown"),
        ("Category", product.get("category", "Unknown")),
        ("Purchase Price", str(model_input["Purchase_Price"])),
        ("Retailer", verified.get("retailer") or product.get("retailer", "Unknown")),
        ("Product Age", f"{model_input['Product_Age_Months']} months"),
        ("Warranty", f"{model_input['Warranty_Duration_Months']} months"),
        ("Fault Type", str(model_input["Fault_Type"])),
        ("Damage Type", str(model_input["Damage_Type"])),
        ("Purchase Proof", str(model_input["Purchase_Proof"])),
        ("Warranty Card", str(model_input["Warranty_Card"])),
        ("Product Image", str(model_input["Product_Image"])),
        ("Serial Evidence", str(model_input["Serial_Number_Evidence"])),
        ("Fault Evidence", str(model_input["Fault_Evidence"])),
        ("Repair Report", str(model_input["Repair_Report"])),
        ("Previous Repairs", str(model_input["Previous_Repair_Count"])),
        ("Repair Center", str(model_input["Repair_Center"]) if pd.notna(model_input["Repair_Center"]) else "None"),
    ]

    left_x, right_x = 40, 420
    box_w, box_h = 340, 52

    for index, (label, value) in enumerate(rows):
        x = left_x if index < 8 else right_x
        row_index = index if index < 8 else index - 8
        y = 112 + row_index * 57
        draw.rounded_rectangle(
            (x, y, x + box_w, y + box_h),
            radius=9, outline="#9ca3af", width=1
        )
        draw.text((x + 12, y + 7), label, fill="#4b5563", font=label_font)
        draw.text((x + 12, y + 27), str(value)[:38], fill="#111827", font=value_font)

    # Explicit anti-leak footer: it describes the card, but contains no answer.
    draw.text(
        (40, 558),
        "Claim facts only | Prepared for independent visual inspection",
        fill="#6b7280", font=small_font
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AssureX Step 6 - corrected Python ML + Claim Summary Card"
    )
    parser.add_argument("--claim", default=str(DEFAULT_CLAIM))
    parser.add_argument("--model", required=True)
    parser.add_argument("--encoder", required=True)
    parser.add_argument("--card", default=str(DEFAULT_CARD))
    parser.add_argument("--prediction", default=str(DEFAULT_PREDICTION))
    args = parser.parse_args()

    claim = json.loads(Path(args.claim).read_text(encoding="utf-8"))

    prediction = run_python_model(
        Path(args.model),
        Path(args.encoder),
        claim,
    )

    generate_summary_card(claim, Path(args.card))

    payload = {
        "claim_id": claim["claim_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "python": prediction,
        "summary_card": {
            "filename": Path(args.card).name,
            "path": str(Path(args.card)),
            "size": "800x600",
            "contains_ai_answer": False,
        },
    }

    out = Path(args.prediction)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print("=" * 68)
    print("ASSUREX - STEP 6: CORRECTED PYTHON MODEL")
    print("=" * 68)
    print(json.dumps(prediction, indent=2))
    print(f"\nSummary Card: {args.card}")
    print(f"Prediction output: {args.prediction}")


if __name__ == "__main__":
    main()
