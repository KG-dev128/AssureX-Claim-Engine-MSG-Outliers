"""
app/services/card_generator.py
Synthetic visual Claim Summary Card generation using Pillow (FR xx).
Constructs clean factual summary images displaying indicators, document statuses,
and policy checks for human reviewers and Google Teachable Machine (GTM) visual model.
CRITICAL SRS RULE: Never includes model predictions or confidence scores on card.
"""
import os
from datetime import datetime
from typing import Dict, Any, Optional
from app.extensions import db
from app.models import Claim, Product, Warranty, Document
from app.services.preprocessing_service import build_feature_dict
from app.utils.hash_utils import compute_sha256


def generate_claim_summary_card(claim_id: str, variation: str = 'default') -> str:
    """
    Generate Claim Summary Card PNG image.
    Variations:
      - 'default': Blue theme, standard card layout
      - 'compact': Dense layout, minimal margins
      - 'dark': Slate / dark theme for visual variety in GTM training
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        # Fallback if Pillow is still installing
        print("[CardGenerator] Pillow not yet available.")
        return ""

    claim = Claim.query.get(claim_id)
    if not claim:
        raise ValueError(f"Claim #{claim_id} not found.")

    product = Product.query.get(claim.product_id)
    warranty = Warranty.query.get(claim.warranty_id)
    features = build_feature_dict(claim_id)

    # Canvas dimensions
    width, height = 800, 950

    # Color themes
    themes = {
        'default': {
            'bg': (248, 250, 252),
            'header_bg': (30, 58, 138),
            'header_text': (255, 255, 255),
            'card_bg': (255, 255, 255),
            'border': (226, 232, 240),
            'section_title': (30, 58, 138),
            'label': (100, 116, 139),
            'val_text': (15, 23, 42),
            'badge_pass': (22, 163, 74),
            'badge_fail': (220, 38, 38),
        },
        'compact': {
            'bg': (241, 245, 249),
            'header_bg': (15, 23, 42),
            'header_text': (255, 255, 255),
            'card_bg': (255, 255, 255),
            'border': (203, 213, 225),
            'section_title': (15, 23, 42),
            'label': (71, 85, 105),
            'val_text': (2, 6, 23),
            'badge_pass': (16, 185, 129),
            'badge_fail': (239, 68, 68),
        },
        'dark': {
            'bg': (15, 23, 42),
            'header_bg': (2, 6, 23),
            'header_text': (248, 250, 252),
            'card_bg': (30, 41, 59),
            'border': (51, 65, 85),
            'section_title': (56, 189, 248),
            'label': (148, 163, 184),
            'val_text': (241, 245, 249),
            'badge_pass': (34, 197, 94),
            'badge_fail': (248, 113, 113),
        }
    }
    t = themes.get(variation, themes['default'])

    img = Image.new('RGB', (width, height), t['bg'])
    draw = ImageDraw.Draw(img)

    # 1. Header
    draw.rectangle([(0, 0), (width, 80)], fill=t['header_bg'])
    draw.text((30, 18), "ASSUREX CLAIM SUMMARY CARD", fill=t['header_text'])
    draw.text((30, 46), f"CLAIM ID: {claim_id[:13].upper()}  |  DATE: {claim.claim_submission_date}", fill=t['header_text'])

    # Section drawer helper
    def draw_section(x, y, w, h, title, fields):
        # Section box
        draw.rectangle([(x, y), (x + w, y + h)], fill=t['card_bg'], outline=t['border'], width=1)
        draw.text((x + 16, y + 12), title.upper(), fill=t['section_title'])
        draw.line([(x + 16, y + 32), (x + w - 16, y + 32)], fill=t['border'], width=1)

        row_y = y + 42
        for lbl, val, *status in fields:
            draw.text((x + 16, row_y), f"{lbl}:", fill=t['label'])
            val_str = str(val)
            color = t['val_text']
            if status:
                color = t['badge_pass'] if status[0] else t['badge_fail']
            draw.text((x + 150, row_y), val_str, fill=color)
            row_y += 24

    # 2. Product Information
    prod_fields = [
        ("Product Name", product.product_name if product else "N/A"),
        ("Category", (product.category if product else "N/A").title()),
        ("Brand / Model", f"{product.brand} / {product.model_number}" if product else "N/A"),
        ("Serial Number", product.serial_number if product else "N/A"),
        ("Purchase Date", str(product.purchase_date if product else "N/A")),
        ("Product Age", f"{int(features['product_age_days'])} days"),
    ]
    draw_section(30, 100, 360, 200, "1. Product Information", prod_fields)

    # 3. Warranty Status
    active = features['is_warranty_active'] == 1.0
    warr_fields = [
        ("Warranty Type", (warranty.warranty_type if warranty else "Standard").title()),
        ("Status", "ACTIVE" if active else "EXPIRED", active),
        ("Expiry Date", str(warranty.expiry_date if warranty else "N/A")),
        ("Days Left", f"{int(features['remaining_warranty_days'])} days", active),
        ("Utilization", f"{features['warranty_utilization_pct'] * 100:.1f}%"),
    ]
    draw_section(410, 100, 360, 200, "2. Warranty Status", warr_fields)

    # 4. Fault Details
    fault_desc = (claim.fault_description or "")[:45]
    fault_fields = [
        ("Damage Type", (claim.damage_type or "Unknown").replace('_', ' ').title()),
        ("Occurrence Date", str(claim.fault_occurrence_date)),
        ("Days Since Fault", f"{int(features['days_since_fault'])} days"),
        ("Fault Category", features['fault_category'].title()),
        ("Description", fault_desc + ("..." if len(claim.fault_description or "") > 45 else "")),
    ]
    draw_section(30, 320, 740, 175, "3. Reported Fault & Condition", fault_fields)

    # 5. Service & Repair History
    is_auth = features['is_authorized_repair'] == 1.0
    repair_fields = [
        ("Prior Repairs", f"{int(features['repair_count'])} incident(s)"),
        ("Authorized Service", "YES" if is_auth else "NO (Violation)", is_auth),
        ("Prior Replacement", "YES" if claim.previous_replacement else "NO"),
    ]
    draw_section(30, 515, 360, 150, "4. Service History", repair_fields)

    # 6. Document Completeness
    doc_fields = [
        ("Purchase Receipt", "PRESENT" if features['has_purchase_receipt'] else "MISSING", features['has_purchase_receipt']),
        ("Warranty Card", "PRESENT" if features['has_warranty_card'] else "NOT PROVIDED", True),
        ("Fault Evidence", "PRESENT" if features['has_fault_evidence'] else "MISSING", features['has_fault_evidence']),
        ("Product Image", "PRESENT" if features['has_product_image'] else "NOT PROVIDED", True),
    ]
    draw_section(410, 515, 360, 150, "5. Uploaded Documents", doc_fields)

    # 7. Verification & Anomaly Checklist
    sn_match = features['serial_number_match'] == 1.0
    no_dup = features['is_duplicate'] == 0.0
    no_contra = features['contradiction_count'] == 0.0
    policy_ok = features['is_excluded_damage'] == 0.0

    checklist = [
        ("Serial Verification", "VERIFIED (MATCH)" if sn_match else "MISMATCH / SUSPICIOUS", sn_match),
        ("Duplicate Check", "CLEAN (NO DUPLICATES)" if no_dup else "DUPLICATE FLAGGED", no_dup),
        ("Chronology & Data", "CONSISTENT" if no_contra else f"{int(features['contradiction_count'])} CONTRADICTION(S)", no_contra),
        ("Policy Exclusion", "COVERED" if policy_ok else "EXCLUDED DAMAGE TYPE", policy_ok),
        ("Missing Docs Count", f"{int(features['missing_doc_count'])} missing", features['missing_doc_count'] == 0),
    ]
    draw_section(30, 685, 740, 185, "6. Anomaly & Compliance Verification", checklist)

    # Footer Notice
    draw.text((30, 890), "CONFIDENTIAL & SYSTEM GENERATED — FOR AUTHORIZED ASSUREX REVIEWERS ONLY", fill=t['label'])
    draw.text((30, 910), f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} | Verification Hash: {claim_id[:16]}", fill=t['label'])

    # Save to disk
    upload_dir = os.path.join('static', 'uploads', claim_id)
    os.makedirs(upload_dir, exist_ok=True)
    card_filename = f"claim_summary_card_{variation}.png"
    card_path = os.path.join(upload_dir, card_filename).replace('\\', '/')

    img.save(card_path, 'PNG')

    # Hash file
    card_hash = compute_sha256(card_path)

    # Record or update in Document table
    existing = Document.query.filter_by(
        claim_id=claim_id,
        doc_type='claim_summary_card',
        file_name=card_filename
    ).first()

    if not existing:
        doc = Document(
            user_id=claim.user_id,
            claim_id=claim.claim_id,
            product_id=claim.product_id,
            doc_type='claim_summary_card',
            file_name=card_filename,
            file_path=card_path,
            file_hash=card_hash,
            file_size=os.path.getsize(card_path),
            mime_type='image/png',
            ocr_status='completed',
        )
        db.session.add(doc)
    else:
        existing.file_hash = card_hash
        existing.file_size = os.path.getsize(card_path)

    db.session.commit()
    return card_path
