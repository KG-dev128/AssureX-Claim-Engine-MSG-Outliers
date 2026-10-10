"""Build a leakage-safe claim-card image corpus from the supplied SRS dataset."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data" / "assurex_claims_full_1500(4).csv"
OUT = ROOT / "data" / "claim_card_dataset"
CLASSES = ["Valid Claim", "Invalid Claim", "Manual Review"]


def as_claim(row: dict) -> dict:
    def yes_no(value: object) -> bool:
        return str(value).strip().lower() in {"yes", "true", "1", "available"}

    flags = {"purchase_receipt": yes_no(row["Purchase_Proof"]),
             "warranty_card": yes_no(row["Warranty_Card"]),
             "product_image": yes_no(row["Product_Image"]),
             "serial_number_evidence": yes_no(row["Serial_Number_Evidence"]),
             "fault_evidence": yes_no(row["Fault_Evidence"]),
             "repair_report": yes_no(row["Repair_Report"])}
    docs = {key: {"filename": "Available evidence"} for key, available in flags.items() if available}
    verified = {"purchase_date": row["Purchase_Date"], "amount_paid": row["Purchase_Price"],
                "warranty_months": row["Warranty_Duration_Months"], "retailer": row["Retailer"],
                "serial_number": row["Serial_Number"], "invoice_number": "Recorded"}
    return {
        "claim_id": row["Claim_ID"], "category": row["Product_Category"],
        "product": {"product_id": row["Product_ID"], "product_name": row["Product_Category"],
                    "category": row["Product_Category"], "brand": row["Brand"], "model": row["Model_Number"],
                    "serial_number": row["Serial_Number"], "purchase_date": row["Purchase_Date"],
                    "purchase_price": row["Purchase_Price"], "warranty_months": row["Warranty_Duration_Months"],
                    "retailer": row["Retailer"]},
        "verified_receipt_data": verified, "documents": docs,
        "fault_date": row["Fault_Occurrence_Date"], "fault_description": row["Fault_Description"],
        "fault_category": row["Fault_Type"], "damage_type": row["Damage_Type"],
        "previous_repair_count": int(row["Previous_Repair_Count"] or 0),
        "previous_repair": int(row["Previous_Repair_Count"] or 0) > 0,
        "previous_replacement": False, "repair_center": row["Repair_Center"],
        "replaced_parts": row["Replaced_Parts"], "unauthorized_repair": str(row["Repair_Authorization"]).lower() == "unauthorized",
        "claim_submission_date": row["Claim_Submission_Date"],
        "extracted_fields": {"_serial_mismatch_warning": "Serial mismatch" if row["Serial_Number_Match"] == "Mismatch" else None},
        "ocr": {key: {"ocr_status": "completed" if value else "not_provided"} for key, value in flags.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    from PIL import Image, ImageEnhance
    import importlib
    summary = importlib.import_module("06_ai_paths").generate_summary_card
    frame = pd.read_csv(args.source, dtype=str, keep_default_na=False)
    if not set(frame["Class_Label"].unique()).issubset(CLASSES) or len(frame["Class_Label"].unique()) != 3:
        raise ValueError("Dataset labels must map to the three SRS claim outcomes.")
    frame["_source_claim_id"] = frame["Claim_ID"]
    # Supplied Claim_IDs are sequential by label; publish random-looking IDs in
    # the structured splits and render that identical ID onto each card.
    frame["Claim_ID"] = frame["Claim_ID"].map(lambda value: "CLM-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16].upper())
    train, remainder = train_test_split(frame, test_size=0.30, random_state=42, stratify=frame["Class_Label"])
    validation, test = train_test_split(remainder, test_size=0.50, random_state=42, stratify=remainder["Class_Label"])
    args.output.mkdir(parents=True, exist_ok=True)
    split_rows = {"training": train, "validation": validation, "testing": test}
    manifest = []
    for split, rows in split_rows.items():
        rows.drop(columns=["_source_claim_id"]).to_csv(args.output / f"{split}.csv", index=False)
        count = 2 if split == "training" else 1
        for record in rows.to_dict(orient="records"):
            label = record["Class_Label"]
            folder = args.output / "cards" / split / label.replace(" ", "_").lower()
            folder.mkdir(parents=True, exist_ok=True)
            for variation in range(count):
                name = f"{record['Claim_ID']}_v{variation+1}.png"
                path = folder / name
                legacy_path = folder / f"{record['_source_claim_id']}_v{variation+1}.png"
                if not path.exists() and legacy_path.is_file():
                    legacy_path.replace(path)
                if path.is_file():
                    # The rest of this card is identical; safely replace the
                    # source's class-correlated sequential ID in-place.
                    from PIL import ImageDraw, ImageFont
                    image = Image.open(path).convert("RGB")
                    draw = ImageDraw.Draw(image)
                    draw.rectangle((35, 65, 380, 91), fill="white")
                    font_path = Path("C:/Windows/Fonts/arial.ttf")
                    font = ImageFont.truetype(str(font_path), 12) if font_path.exists() else ImageFont.load_default()
                    draw.text((38, 70), f"Claim ID: {record['Claim_ID']}", fill="#4b5563", font=font)
                    image.save(path, format="PNG")
                else:
                    summary(as_claim(record), path)
                if variation:
                    image = Image.open(path).convert("RGB")
                    image = ImageEnhance.Contrast(image).enhance(0.98)
                    image.save(path)
                manifest.append({"claim_id": record["Claim_ID"], "source_claim_id": record["_source_claim_id"], "split": split,
                                 "label": label, "variation": variation + 1,
                                 "image": path.relative_to(args.output).as_posix(),
                                 "source": args.source.name})
    with (args.output / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest[0]))
        writer.writeheader(); writer.writerows(manifest)
    (args.output / "label_mapping.json").write_text(json.dumps({"class_order": CLASSES,
        "mapping_source": "Class_Label column in supplied AssureX SRS dataset",
        "contains_claim_outcome_on_image": False,
        "source_claim_id_rendered": False,
        "card_reference": "deterministic SHA-256 pseudonym of source claim ID",
        "splitting": "stratified by class; all variations of a claim stay in one split",
        "counts": {split: {label: int((rows["Class_Label"] == label).sum()) for label in CLASSES}
                   for split, rows in split_rows.items()}}, indent=2), encoding="utf-8")
    print(f"Built {len(train)*2} training, {len(validation)} validation, {len(test)} test cards from {len(frame)} source claims.")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
