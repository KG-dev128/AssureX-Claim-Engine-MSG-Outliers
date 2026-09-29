"""
app/services/report_generator.py
Comprehensive report generation service for claims, audit logs, and analytics (FR xli, xlii).
Generates structured PDF reports using ReportLab (with HTML/text fallback) and CSV analytics exports.
"""
import os
import csv
import io
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.models import Claim, Product, Warranty, ClaimDecision, RuleValidationResult, User, Document


def generate_claim_pdf_report(claim_id: str) -> str:
    """
    Generates a formal evaluation PDF report for a claim.
    Saves to static/uploads/<claim_id>/claim_evaluation_report.pdf
    """
    claim = Claim.query.get(claim_id)
    if not claim:
        raise ValueError(f"Claim #{claim_id} not found.")

    product = Product.query.get(claim.product_id)
    warranty = Warranty.query.get(claim.warranty_id)
    decision = ClaimDecision.query.filter_by(claim_id=claim_id).first()
    rules = RuleValidationResult.query.filter_by(claim_id=claim_id).all()
    user = User.query.get(claim.user_id)

    out_dir = os.path.join('static', 'uploads', claim_id)
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, 'claim_evaluation_report.pdf').replace('\\', '/')

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        doc = SimpleDocTemplate(pdf_path, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1e3a8a'),
            spaceAfter=10
        )
        sub_style = ParagraphStyle(
            'ReportSub',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#475569'),
            spaceAfter=15
        )

        elements.append(Paragraph("ASSUREX CLAIM ENGINE — FORMAL EVALUATION REPORT", title_style))
        elements.append(Paragraph(f"Generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} | Document Ref: {claim_id[:12].upper()}", sub_style))
        elements.append(Spacer(1, 10))

        # Metadata Table
        claim_data = [
            ["Claim ID", claim.claim_id, "Status", claim.status.upper()],
            ["Claimant", user.username if user else "N/A", "Submission Date", str(claim.claim_submission_date)],
            ["Product", product.product_name if product else "N/A", "Category", product.category.title() if product else "N/A"],
            ["Serial No.", product.serial_number if product else "N/A", "Warranty Expiry", str(warranty.expiry_date if warranty else "N/A")],
            ["Fault Type", (claim.damage_type or "Unknown").replace('_', ' ').title(), "Fault Date", str(claim.fault_occurrence_date)],
        ]
        t1 = Table(claim_data, colWidths=[100, 170, 100, 170])
        t1.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t1)
        elements.append(Spacer(1, 15))

        # Decision Section
        if decision:
            elements.append(Paragraph("AI & DETERMINISTIC SYNTHESIS DECISION", styles['Heading2']))
            dec_data = [
                ["Final Decision", decision.final_decision.replace('_', ' ').upper()],
                ["Python Model Output", f"{decision.python_predicted_class} (conf: {float(decision.python_top_confidence or 0):.2f})"],
                ["GTM Visual Model Output", f"{decision.gtm_predicted_class} (conf: {float(decision.gtm_top_confidence or 0):.2f})"],
                ["Model Consistency Status", decision.consistency_status.replace('_', ' ').title()],
                ["Confidence Difference", f"{float(decision.confidence_difference or 0):.4f}"],
                ["Rules Passed / Failed", f"{decision.rules_passed_count} Passed / {decision.rules_failed_count} Failed"],
                ["Missing Documents", str(decision.missing_doc_count)],
                ["Contradictions Detected", str(decision.contradiction_count)],
                ["Duplicate Submission", "YES" if decision.is_duplicate else "NO"],
            ]
            t2 = Table(dec_data, colWidths=[200, 340])
            t2.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f5f9')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(t2)
            elements.append(Spacer(1, 15))

        # 14-Rule Breakdown Table
        elements.append(Paragraph("14 DETERMINISTIC BUSINESS RULES BREAKDOWN", styles['Heading2']))
        rule_rows = [["Rule Identifier", "Status", "Details"]]
        for r in rules:
            status_text = "PASS" if r.rule_passed else "FAIL"
            rule_rows.append([r.rule_name, status_text, (r.details or "")[:60]])

        t3 = Table(rule_rows, colWidths=[180, 60, 300])
        t3.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(t3)

        doc.build(elements)
        return pdf_path

    except ImportError:
        # Fallback text file report if ReportLab is not available
        with open(pdf_path.replace('.pdf', '.txt'), 'w', encoding='utf-8') as f:
            f.write(f"ASSUREX CLAIM REPORT: {claim_id}\n")
            f.write(f"Product: {product.product_name if product else 'N/A'}\n")
            f.write(f"Status: {claim.status}\n")
            if decision:
                f.write(f"Decision: {decision.final_decision}\n")
        return pdf_path.replace('.pdf', '.txt')


def generate_claims_csv(user_id: Optional[str] = None) -> io.StringIO:
    """Generate CSV export of claims dataset."""
    query = Claim.query
    if user_id:
        query = query.filter_by(user_id=user_id)
    claims = query.order_by(Claim.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'claim_id', 'user_id', 'product_name', 'category', 'serial_number',
        'damage_type', 'fault_date', 'submission_date', 'status',
        'missing_docs', 'contradictions', 'is_duplicate', 'final_decision'
    ])

    for c in claims:
        p = Product.query.get(c.product_id)
        d = ClaimDecision.query.filter_by(claim_id=c.claim_id).first()
        writer.writerow([
            c.claim_id,
            c.user_id,
            p.product_name if p else '',
            p.category if p else '',
            p.serial_number if p else '',
            c.damage_type or '',
            str(c.fault_occurrence_date),
            str(c.claim_submission_date),
            c.status,
            c.missing_doc_count,
            c.contradiction_count,
            1 if c.is_duplicate else 0,
            d.final_decision if d else ''
        ])

    output.seek(0)
    return output
