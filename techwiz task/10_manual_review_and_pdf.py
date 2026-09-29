"""
ASSUREX - STEP 10
Manual review + append-only audit trail + PDF audit certificate.

The audit trail uses hash chaining. This is a practical demo-friendly way to
make old entries tamper-evident: each record includes the hash of the previous
record and its own SHA-256 hash.

PDF generation uses ReportLab.

Run:
    python 10_manual_review_and_pdf.py --decision outputs/step09_final_decision.json --claim outputs/step05_verified_claim.json

Package:
    pip install reportlab
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
AUDIT_PATH = BASE_DIR / "data" / "audit_trail.jsonl"
DEFAULT_DECISION = OUTPUT_DIR / "step09_final_decision.json"
DEFAULT_CLAIM = OUTPUT_DIR / "step05_verified_claim.json"
DEFAULT_PDF = OUTPUT_DIR / "assurex_audit_certificate.pdf"


def append_audit_record(record: dict) -> dict:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    previous_hash = "GENESIS"
    if AUDIT_PATH.exists():
        last_line = ""
        for line in AUDIT_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last_line = line
        if last_line:
            previous_hash = json.loads(last_line)["record_hash"]

    record = dict(record)
    record["previous_record_hash"] = previous_hash
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    record["record_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    with AUDIT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def build_pdf(pdf_path: Path, decision: dict, claim: dict, reviewer: dict) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=A4,
        rightMargin=16 * mm, leftMargin=16 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title="AssureX Claim Audit Certificate",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("Title2", parent=styles["Title"], fontSize=22, leading=26, textColor=colors.HexColor("#111827"))
    heading = ParagraphStyle("Heading2", parent=styles["Heading2"], fontSize=13, leading=16, textColor=colors.HexColor("#1f2937"))
    body = ParagraphStyle("Body2", parent=styles["BodyText"], fontSize=9.5, leading=13, textColor=colors.HexColor("#374151"))

    story = [
        Paragraph("ASSUREX CLAIM ENGINE", title),
        Paragraph("Warranty Claim Audit Certificate", heading),
        Spacer(1, 8),
    ]

    claim_data = [
        ["Claim ID", claim.get("claim_id", "N/A")],
        ["Account ID", claim.get("user_id", "N/A")],
        ["Product", f"{claim.get('product', {}).get('brand', '')} {claim.get('product', {}).get('model', '')}"],
        ["Category / serial", f"{claim.get('product', {}).get('category', 'N/A')} / {claim.get('product', {}).get('serial_number', 'N/A')}"],
        ["Purchase date / price", f"{claim.get('verified_receipt_data', {}).get('purchase_date', 'N/A')} / {claim.get('verified_receipt_data', {}).get('amount_paid', 'N/A')}"],
        ["Fault", claim.get("fault_description", "N/A")],
        ["Fault date / damage", f"{claim.get('fault_date', 'N/A')} / {claim.get('damage_type', 'N/A')}"],
        ["Final Decision", decision.get("decision", "N/A")],
        ["Reviewer", reviewer.get("reviewer", "System")],
        ["Review Action", reviewer.get("action", "Not required")],
        ["Review Reason", reviewer.get("reason", "N/A")],
    ]
    table = Table(claim_data, colWidths=[42 * mm, 130 * mm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [table, Spacer(1, 12)]

    story.append(Paragraph("AI & Rule Summary", heading))
    story.append(Spacer(1, 5))
    ai = decision.get("ai_results", {})
    for title_text, key in (("Python classification model", "python"), ("Independent image model", "image_model")):
        prediction = ai.get(key, {}) or {}
        story.append(Paragraph(escape(f"{title_text}: {prediction.get('prediction') or 'Unavailable'}"), body))
        for class_name, confidence in (prediction.get("confidences") or {}).items():
            story.append(Paragraph(escape(f"{class_name}: {float(confidence):.1%}"), body))
        if prediction.get("model_version") or prediction.get("model_file") or prediction.get("model"):
            story.append(Paragraph(escape(f"Model version: {prediction.get('model_version') or prediction.get('model_file') or prediction.get('model')}"), body))
    comparison = ai.get("comparison", {}) or {}
    story.append(Paragraph(escape(f"Model comparison: {comparison.get('consistency_status', 'Unavailable')}"), body))
    if comparison.get("confidence_difference") is not None:
        story.append(Paragraph(escape(f"Top-class confidence difference: {float(comparison['confidence_difference']):.1%}"), body))
    warranty = decision.get("warranty", {})
    story.append(Paragraph(f"Policy rules: {warranty.get('rule_status', 'Not assessed')}", body))
    for group, key in (("Passed", "passed_rules"), ("Warnings", "warnings"),
                       ("Failed", "hard_failures"), ("Manual review", "manual_review_flags"),
                       ("Missing documents", "missing_documents")):
        values = warranty.get(key) or []
        if values:
            story.append(Paragraph(escape(f"{group}: {'; '.join(map(str, values))}"), body))

    documents = claim.get("documents", {}) or {}
    if documents:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Evidence register", heading))
        for name, evidence in documents.items():
            if evidence:
                story.append(Paragraph(escape(f"{name}: {evidence.get('filename', 'file')} · SHA-256 {evidence.get('sha256', 'not recorded')}"), body))
    for key, label in (("duplicate_claim_flags", "Duplicate claim flags"),
                       ("contradiction_flags", "Contradictions"),
                       ("duplicate_flags", "Duplicate documents")):
        values = claim.get(key) or []
        if values:
            story.append(Paragraph(escape(f"{label}: {'; '.join(map(str, values))}"), body))

    story += [Spacer(1, 12), Paragraph("Decision Explanation", heading), Spacer(1, 5)]
    story.append(Paragraph(escape(str(decision.get("explanation", "N/A"))), body))
    story += [Spacer(1, 12), Paragraph("Audit Record Hash", heading), Spacer(1, 5)]
    story.append(Paragraph(reviewer.get("record_hash", "N/A"), body))
    story.append(Spacer(1, 14))
    story.append(Paragraph("Generated by AssureX Claim Engine. Historical AI results and reviewer actions should remain preserved in the audit trail.", body))

    doc.build(story)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AssureX Step 10 - manual review and PDF report"
    )
    parser.add_argument("--decision", default=str(DEFAULT_DECISION))
    parser.add_argument("--claim", default=str(DEFAULT_CLAIM))
    parser.add_argument(
        "--comparison",
        default=str(OUTPUT_DIR / "step07_comparison.json"),
    )
    parser.add_argument(
        "--warranty",
        default=str(OUTPUT_DIR / "step08_warranty_result.json"),
    )
    parser.add_argument("--pdf", default=str(DEFAULT_PDF))
    args = parser.parse_args()

    decision = json.loads(
        Path(args.decision).read_text(encoding="utf-8")
    )
    claim = json.loads(
        Path(args.claim).read_text(encoding="utf-8")
    )

    comparison = {}
    warranty = {}

    if Path(args.comparison).exists():
        comparison = json.loads(
            Path(args.comparison).read_text(encoding="utf-8")
        )

    if Path(args.warranty).exists():
        warranty = json.loads(
            Path(args.warranty).read_text(encoding="utf-8")
        )

    print("=" * 68)
    print("ASSUREX - STEP 10: REVIEW + AUDIT + PDF")
    print("=" * 68)
    print(f"Claim: {decision.get('claim_id')}")
    print(f"Automated recommendation: {decision.get('decision')}")

    reviewer = {
        "reviewer": "System",
        "action": "Not Required",
        "reason": "Automated result did not require human override.",
    }

    if decision.get("manual_review_required"):
        print("\nManual review is required.")
        reviewer = {
            "reviewer": ask("Reviewer name"),
            "action": ask(
                "Action (Approve / Reject / Request Information)",
                "Request Information",
            ),
            "reason": ask("Mandatory review reason"),
        }

    ai_results = decision.get("ai_results", {})

    audit = append_audit_record({
        "event_id": "AUD-" + secrets.token_hex(6).upper(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "claim_id": claim["claim_id"],
        "automated_decision": decision.get("decision"),

        # Preserve the original AI evidence exactly as returned.
        "python_prediction": ai_results.get("python", {}).get("prediction"),
        "python_confidences": ai_results.get("python", {}).get(
            "confidences", {}
        ),
        "tm_prediction": ai_results.get(
            "teachable_machine", {}
        ).get("prediction"),
        "tm_confidences": ai_results.get(
            "teachable_machine", {}
        ).get("confidences", {}),
        "consistency_status": ai_results.get(
            "comparison", {}
        ).get("consistency_status"),
        "confidence_difference": ai_results.get(
            "comparison", {}
        ).get("confidence_difference"),

        "warranty_rule_status": warranty.get("rule_status"),
        "warranty_hard_failures": warranty.get("hard_failures", []),
        "warranty_manual_flags": warranty.get(
            "manual_review_flags", []
        ),

        "reviewer": reviewer["reviewer"],
        "action": reviewer["action"],
        "reason": reviewer["reason"],
        "source": "AssureX",
    })

    reviewer["record_hash"] = audit["record_hash"]

    review_path = OUTPUT_DIR / "step10_review_audit.json"
    review_path.write_text(
        json.dumps(
            {
                "decision": decision,
                "reviewer": reviewer,
                "audit_record": audit,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    build_pdf(Path(args.pdf), decision, claim, reviewer)

    print(f"\nAudit record: {review_path}")
    print(f"Audit PDF: {args.pdf}")


if __name__ == "__main__":
    main()
