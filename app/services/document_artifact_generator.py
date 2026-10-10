"""
app/services/document_artifact_generator.py
Synthetic artifact generation for Products and Claims as per policy requirements.
Generates:
1. Official Retailer Receipt / Invoice (PNG) with OCR-compatible metadata
2. Warranty Protection Card / Certificate (PNG) with statutory terms & QR seal
3. Hardware Defect Telemetry & Failure Proof (PNG)
4. Product Overview / Serial Number Chassis Photo (PNG)
5. Authorized Service Center Repair Report (PNG)
"""
import os
import uuid
import hashlib
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List
from PIL import Image, ImageDraw, ImageFont

from app.extensions import db
from app.models import Product, Warranty, Document, Claim, RepairHistory
from app.services.policy_service import load_policy
from app.services.audit_service import log_action


def _get_font(size: int = 14, bold: bool = False):
    """Load default font or fallback font gracefully."""
    font_paths = [
        "arialbd.ttf" if bold else "arial.ttf",
        "Arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _compute_sha256(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


# ── 1. RECEIPT GENERATOR ─────────────────────────────────────────────────────

def generate_receipt_artifact(
    product: Product,
    claim: Optional[Claim] = None,
    override_serial: Optional[str] = None,
    retailer_name: Optional[str] = None
) -> Document:
    """
    Generates an authentic optical store receipt image matching product specifications.
    Embeds clear OCR-extractable retailer name, invoice number, purchase date, and serial number.
    """
    subfolder = claim.claim_id if claim else product.product_id
    out_dir = os.path.join('static', 'uploads', subfolder)
    _ensure_dir(out_dir)

    inv_id = f"INV-2026-{uuid.uuid4().hex[:8].upper()}"
    pdate_str = product.purchase_date.strftime("%Y-%m-%d")
    retailer = retailer_name or product.retailer or "Official Authorized Store"
    serial = override_serial or product.serial_number
    price = float(product.purchase_price or 799.00)
    tax = round(price * 0.0825, 2)
    total = round(price + tax, 2)

    width, height = 550, 780
    img = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    f_title = _get_font(20, bold=True)
    f_sub = _get_font(12, bold=False)
    f_bold = _get_font(13, bold=True)
    f_norm = _get_font(12, bold=False)
    f_mono = _get_font(13, bold=True)
    f_small = _get_font(10, bold=False)

    # Top Header
    draw.rectangle([(0, 0), (width, 85)], fill=(24, 51, 39))  # Luxury forest green
    draw.text((width // 2, 28), retailer.upper(), fill=(255, 255, 255), font=f_title, anchor="mm")
    draw.text((width // 2, 58), "OFFICIAL TAX INVOICE & PROOF OF PURCHASE", fill=(195, 172, 142), font=f_sub, anchor="mm")

    y = 105
    draw.text((35, y), f"INVOICE NO:  {inv_id}", fill=(15, 23, 42), font=f_bold)
    draw.text((width - 35, y), f"DATE: {pdate_str}", fill=(15, 23, 42), font=f_bold, anchor="ra")

    y += 26
    draw.text((35, y), f"TERMINAL: REG-04 · CASHIER: #209", fill=(100, 116, 139), font=f_small)
    draw.text((width - 35, y), "STATUS: PAID IN FULL", fill=(22, 163, 74), font=f_bold, anchor="ra")

    y += 24
    draw.line([(35, y), (width - 35, y)], fill=(203, 213, 225), width=1)

    # Item details
    y += 20
    draw.text((35, y), "ITEM DESCRIPTION", fill=(100, 116, 139), font=f_small)
    draw.text((width - 35, y), "AMOUNT (USD)", fill=(100, 116, 139), font=f_small, anchor="ra")

    y += 22
    draw.text((35, y), product.product_name[:38], fill=(15, 23, 42), font=f_bold)
    draw.text((width - 35, y), f"${price:,.2f}", fill=(15, 23, 42), font=f_bold, anchor="ra")

    y += 20
    draw.text((35, y), f"Brand: {product.brand} · Model: {product.model_number}", fill=(71, 85, 105), font=f_norm)

    y += 22
    # Serial Box highlight
    draw.rectangle([(35, y), (width - 35, y + 36)], fill=(241, 245, 249), outline=(203, 213, 225), width=1)
    draw.text((45, y + 18), f"HARDWARE S/N: {serial}", fill=(24, 51, 39), font=f_mono, anchor="lm")
    draw.text((width - 45, y + 18), f"CAT: {product.category.upper()}", fill=(140, 107, 75), font=f_bold, anchor="rm")

    y += 56
    draw.text((35, y), f"WARRANTY PERIOD: {product.warranty_duration_months} MONTHS (OEM STATUTORY)", fill=(71, 85, 105), font=f_norm)

    y += 30
    draw.line([(35, y), (width - 35, y)], fill=(203, 213, 225), width=1)

    # Financial Breakdown
    y += 18
    draw.text((35, y), "Subtotal:", fill=(71, 85, 105), font=f_norm)
    draw.text((width - 35, y), f"${price:,.2f}", fill=(15, 23, 42), font=f_norm, anchor="ra")

    y += 22
    draw.text((35, y), "Estimated Sales Tax (8.25%):", fill=(71, 85, 105), font=f_norm)
    draw.text((width - 35, y), f"${tax:,.2f}", fill=(15, 23, 42), font=f_norm, anchor="ra")

    y += 26
    draw.line([(35, y), (width - 35, y)], fill=(24, 51, 39), width=2)

    y += 14
    draw.text((35, y), "TOTAL PAID:", fill=(24, 51, 39), font=f_title)
    draw.text((width - 35, y), f"${total:,.2f}", fill=(24, 51, 39), font=f_title, anchor="ra")

    y += 48
    draw.text((35, y), "PAYMENT METHOD: VISA ENDING IN 4092 · AUTH: #883921", fill=(100, 116, 139), font=f_small)

    # Barcode representation
    y += 36
    draw.rectangle([(width // 2 - 160, y), (width // 2 + 160, y + 48)], fill=(15, 23, 42))
    # Draw barcode stripes
    for bar_x in range(width // 2 - 150, width // 2 + 150, 6):
        draw.line([(bar_x, y + 4), (bar_x, y + 44)], fill=(255, 255, 255), width=2)

    y += 62
    draw.text((width // 2, y), f"* {inv_id} *", fill=(15, 23, 42), font=f_mono, anchor="mm")

    y += 34
    draw.text((width // 2, y), "Thank you for your purchase! Retain this receipt for all warranty claims.", fill=(100, 116, 139), font=f_small, anchor="mm")
    draw.text((width // 2, y + 16), "AssureX Verified Optical Invoice · Fully Statutory & Magnuson-Moss Compliant", fill=(140, 107, 75), font=f_small, anchor="mm")

    file_name = f"receipt_{uuid.uuid4().hex[:8]}.png"
    file_path = os.path.join(out_dir, file_name)
    img.save(file_path, "PNG")

    file_hash = _compute_sha256(file_path)
    file_size = os.path.getsize(file_path)

    # Structured OCR extraction metadata matching real OCR format
    ocr_data = {
        'retailer_name': retailer,
        'retailer': retailer,
        'invoice_number': inv_id,
        'purchase_date': pdate_str,
        'serial_number': serial,
        'total_amount': total,
        'product_name': product.product_name,
        'brand': product.brand,
        'model_number': product.model_number,
        'confidences': {
            'retailer_name': 0.98,
            'retailer': 0.98,
            'invoice_number': 0.99,
            'purchase_date': 0.96,
            'serial_number': 0.97,
            'total_amount': 0.99,
        }
    }


    doc = Document(
        user_id=product.user_id,
        product_id=product.product_id,
        claim_id=claim.claim_id if claim else None,
        doc_type='receipt',
        file_name=file_name,
        file_path=file_path,
        file_hash=file_hash,
        file_size=file_size,
        mime_type='image/png',
        ocr_extracted_data=ocr_data,
        ocr_status='completed'
    )
    db.session.add(doc)
    db.session.commit()
    return doc


# ── 2. WARRANTY CERTIFICATE CARD GENERATOR ───────────────────────────────────

def generate_warranty_card_artifact(
    product: Product,
    warranty: Optional[Warranty] = None,
    claim: Optional[Claim] = None
) -> Document:
    """
    Generates a luxury certificate of warranty protection card.
    Contains product specifications, validity dates, QR verification seal, and policy terms.
    """
    if warranty is None:
        warranty = product.warranties.first()
        if not warranty:
            from datetime import timedelta
            start = product.purchase_date or date.today()
            expiry = start + timedelta(days=365)
            warranty = Warranty(
                product_id=product.product_id,
                warranty_type='standard',
                start_date=start,
                expiry_date=expiry,
                is_active=True
            )
            db.session.add(warranty)
            db.session.commit()

    subfolder = claim.claim_id if claim else product.product_id
    out_dir = os.path.join('static', 'uploads', subfolder)
    _ensure_dir(out_dir)

    policy = load_policy(product.category)

    covered = ", ".join([d.replace('_', ' ').title() for d in policy.get('covered_damage_types', [])[:3]])
    excluded = ", ".join([d.replace('_', ' ').title() for d in policy.get('excluded_damage_types', [])[:3]])

    width, height = 800, 520
    img = Image.new('RGB', (width, height), color=(248, 246, 240))  # Warm luxury parchment
    draw = ImageDraw.Draw(img)

    f_title = _get_font(22, bold=True)
    f_sub = _get_font(13, bold=False)
    f_bold = _get_font(13, bold=True)
    f_norm = _get_font(12, bold=False)
    f_mono = _get_font(13, bold=True)
    f_small = _get_font(11, bold=False)

    # Double Border
    draw.rectangle([(16, 16), (width - 16, height - 16)], outline=(24, 51, 39), width=3)
    draw.rectangle([(22, 22), (width - 22, height - 22)], outline=(195, 172, 142), width=1)

    # Header Ribbon
    draw.rectangle([(24, 24), (width - 24, 100)], fill=(24, 51, 39))
    draw.text((width // 2, 50), "ASSUREX WARRANTY PROTECTION CERTIFICATE", fill=(255, 255, 255), font=f_title, anchor="mm")
    draw.text((width // 2, 78), f"OFFICIAL OEM COVERAGE · {product.category.upper()} POLICY TIERS", fill=(195, 172, 142), font=f_sub, anchor="mm")

    y = 125
    draw.text((45, y), "CERTIFICATE HOLDER & DEVICE SPECIFICATION", fill=(140, 107, 75), font=f_bold)
    draw.text((width - 45, y), f"WARRANTY ID: {warranty.warranty_id}", fill=(24, 51, 39), font=f_mono, anchor="ra")

    y += 24
    draw.line([(45, y), (width - 45, y)], fill=(203, 213, 225), width=1)

    y += 18
    draw.text((45, y), "Product Name:", fill=(100, 116, 139), font=f_norm)
    draw.text((160, y), product.product_name, fill=(15, 23, 42), font=f_bold)

    draw.text((460, y), "Category:", fill=(100, 116, 139), font=f_norm)
    draw.text((560, y), product.category.upper(), fill=(15, 23, 42), font=f_bold)

    y += 24
    draw.text((45, y), "Brand & Model:", fill=(100, 116, 139), font=f_norm)
    draw.text((160, y), f"{product.brand} ({product.model_number})", fill=(15, 23, 42), font=f_norm)

    draw.text((460, y), "Coverage Tier:", fill=(100, 116, 139), font=f_norm)
    draw.text((560, y), (warranty.warranty_type or 'standard').upper(), fill=(22, 163, 74), font=f_bold)

    y += 24
    draw.text((45, y), "Registered S/N:", fill=(100, 116, 139), font=f_norm)
    draw.text((160, y), product.serial_number, fill=(24, 51, 39), font=f_mono)

    draw.text((460, y), "Provider:", fill=(100, 116, 139), font=f_norm)
    draw.text((560, y), warranty.provider or "AssureX Direct OEM", fill=(15, 23, 42), font=f_norm)

    # Dates Highlight Card
    y += 36
    draw.rectangle([(45, y), (width - 45, y + 60)], fill=(241, 245, 249), outline=(195, 172, 142), width=1)

    start_str = warranty.start_date.strftime("%Y-%m-%d") if warranty.start_date else product.purchase_date.strftime("%Y-%m-%d")
    expiry_str = warranty.expiry_date.strftime("%Y-%m-%d") if warranty.expiry_date else "—"

    draw.text((80, y + 30), f"EFFECTIVE FROM: {start_str}", fill=(15, 23, 42), font=f_bold, anchor="lm")
    draw.text((width // 2, y + 30), f"VALID UNTIL: {expiry_str}", fill=(24, 51, 39), font=f_title, anchor="mm")
    draw.text((width - 80, y + 30), "STATUS: ACTIVE", fill=(22, 163, 74), font=f_bold, anchor="rm")

    y += 80
    draw.text((45, y), "STATUTORY TERMS & PERILS SUMMARY", fill=(140, 107, 75), font=f_bold)

    y += 22
    draw.text((45, y), f"✓ Covered Perils: {covered}", fill=(22, 163, 74), font=f_norm)
    y += 20
    draw.text((45, y), f"✗ Policy Exclusions: {excluded}", fill=(220, 38, 38), font=f_norm)

    # Footer verification seal
    y += 36
    draw.line([(45, y), (width - 45, y)], fill=(203, 213, 225), width=1)

    y += 20
    draw.text((45, y), "AssureX Global Enterprise Warranty Infrastructure · Cryptographically Certified", fill=(100, 116, 139), font=f_small)
    draw.text((width - 45, y), "SEAL: [VERIFIED AUTHENTIC]", fill=(24, 51, 39), font=f_mono, anchor="ra")

    file_name = f"warranty_card_{uuid.uuid4().hex[:8]}.png"
    file_path = os.path.join(out_dir, file_name)
    img.save(file_path, "PNG")

    file_hash = _compute_sha256(file_path)
    file_size = os.path.getsize(file_path)

    doc = Document(
        user_id=product.user_id,
        product_id=product.product_id,
        claim_id=claim.claim_id if claim else None,
        doc_type='warranty_card',
        file_name=file_name,
        file_path=file_path,
        file_hash=file_hash,
        file_size=file_size,
        mime_type='image/png',
        ocr_extracted_data={
            'warranty_id': warranty.warranty_id,
            'serial_number': product.serial_number,
            'start_date': start_str,
            'expiry_date': expiry_str,
            'provider': warranty.provider,
            'product_name': product.product_name
        },
        ocr_status='completed'
    )
    db.session.add(doc)
    db.session.commit()
    return doc


# ── 3. DEFECT EVIDENCE & TELEMETRY GENERATOR ─────────────────────────────────

def generate_fault_evidence_artifact(
    product: Product,
    claim: Optional[Claim] = None,
    damage_type: Optional[str] = None,
    fault_description: Optional[str] = None
) -> Document:
    """
    Generates high-contrast visual defect evidence / diagnostic telemetry graphic
    for machine inspection (Teachable Machine) and human review audit.
    """
    subfolder = claim.claim_id if claim else product.product_id
    out_dir = os.path.join('static', 'uploads', subfolder)
    _ensure_dir(out_dir)

    dmg = damage_type or (claim.damage_type if claim else "electrical_failure")
    desc = fault_description or (claim.fault_description if claim else "Hardware operational malfunction reported.")

    width, height = 750, 550
    img = Image.new('RGB', (width, height), color=(15, 23, 42))  # Dark telemetry background
    draw = ImageDraw.Draw(img)

    f_title = _get_font(20, bold=True)
    f_sub = _get_font(12, bold=False)
    f_bold = _get_font(13, bold=True)
    f_norm = _get_font(12, bold=False)
    f_mono = _get_font(13, bold=True)
    f_code = _get_font(11, bold=True)

    # Top Telemetry Header
    draw.rectangle([(0, 0), (width, 70)], fill=(30, 41, 59))
    draw.text((30, 35), "ASSUREX DIAGNOSTIC TELEMETRY & HARDWARE DEFECT EVIDENCE", fill=(255, 255, 255), font=f_title, anchor="lm")

    y = 90
    draw.text((30, y), f"TEST UNIT: {product.product_name.upper()}", fill=(241, 245, 249), font=f_bold)
    draw.text((width - 30, y), f"S/N: {product.serial_number}", fill=(56, 189, 248), font=f_mono, anchor="ra")

    y += 24
    draw.text((30, y), f"CATEGORY: {product.category.upper()} · TEST BENCH: #TB-09 · ISO-17025 VERIFIED", fill=(148, 163, 184), font=f_sub)

    # Oscilloscope / Telemetry Visual Box
    y += 25
    draw.rectangle([(30, y), (width - 30, y + 180)], fill=(2, 6, 23), outline=(51, 65, 85), width=2)

    # Draw grid lines
    for gx in range(50, width - 30, 50):
        draw.line([(gx, y), (gx, y + 180)], fill=(30, 41, 59), width=1)
    for gy in range(y + 30, y + 180, 30):
        draw.line([(30, gy), (width - 30, gy)], fill=(30, 41, 59), width=1)

    # Draw defect waveform / signal pulse
    coords = [
        (40, y + 90), (120, y + 90), (150, y + 30), (170, y + 150),
        (200, y + 80), (280, y + 90), (320, y + 40), (340, y + 160),
        (380, y + 90), (500, y + 90), (530, y + 20), (550, y + 170),
        (600, y + 90), (710, y + 90)
    ]
    draw.line(coords, fill=(239, 68, 68), width=3)  # Red anomalous defect pulse

    draw.text((50, y + 20), "CH-1: POWER RAIL IMPEDANCE", fill=(248, 113, 113), font=f_code)
    draw.text((50, y + 155), f"ANOMALOUS TRIP EVENT DETECTED: {dmg.upper()}", fill=(239, 68, 68), font=f_bold)

    # Damage Description Box
    y += 205
    draw.rectangle([(30, y), (width - 30, y + 90)], fill=(30, 41, 59), outline=(71, 85, 105), width=1)
    draw.text((45, y + 16), "DIAGNOSTIC SYMPTOM STATEMENT:", fill=(148, 163, 184), font=f_code)
    draw.text((45, y + 40), desc[:90], fill=(241, 245, 249), font=f_norm)
    if len(desc) > 90:
        draw.text((45, y + 60), desc[90:180], fill=(241, 245, 249), font=f_norm)

    # Footer verification stamps
    y += 115
    draw.line([(30, y), (width - 30, y)], fill=(51, 65, 85), width=1)

    y += 18
    draw.text((30, y), f"TIMESTAMP: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} · HARDWARE FRACTURE LOG", fill=(148, 163, 184), font=f_sub)
    draw.text((width - 30, y), "STATUS: DEFECT CONFIRMED ✓", fill=(34, 197, 94), font=f_bold, anchor="ra")

    file_name = f"fault_evidence_{uuid.uuid4().hex[:8]}.png"
    file_path = os.path.join(out_dir, file_name)
    img.save(file_path, "PNG")

    file_hash = _compute_sha256(file_path)
    file_size = os.path.getsize(file_path)

    doc = Document(
        user_id=product.user_id,
        product_id=product.product_id,
        claim_id=claim.claim_id if claim else None,
        doc_type='fault_evidence',
        file_name=file_name,
        file_path=file_path,
        file_hash=file_hash,
        file_size=file_size,
        mime_type='image/png',
        ocr_extracted_data={
            'evidence_type': 'diagnostic_telemetry',
            'damage_type': dmg,
            'serial_number': product.serial_number,
            'defect_confirmed': True
        },
        ocr_status='completed'
    )
    db.session.add(doc)
    db.session.commit()
    return doc


# ── 4. REPAIR REPORT ARTIFACT GENERATOR ──────────────────────────────────────

def generate_repair_report_artifact(
    product: Product,
    repair: Optional[RepairHistory] = None,
    claim: Optional[Claim] = None
) -> Document:
    """Generates official OEM service center repair order invoice."""
    subfolder = claim.claim_id if claim else product.product_id
    out_dir = os.path.join('static', 'uploads', subfolder)
    _ensure_dir(out_dir)

    center = repair.repair_center if repair else "AssureX Authorized Service Center"
    rdate = repair.repair_date.strftime("%Y-%m-%d") if repair else date.today().strftime("%Y-%m-%d")

    width, height = 650, 500
    img = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    f_title = _get_font(18, bold=True)
    f_bold = _get_font(13, bold=True)
    f_norm = _get_font(12, bold=False)
    f_mono = _get_font(13, bold=True)
    f_small = _get_font(10, bold=False)

    draw.rectangle([(0, 0), (width, 70)], fill=(30, 58, 138))
    draw.text((width // 2, 26), center.upper(), fill=(255, 255, 255), font=f_title, anchor="mm")
    draw.text((width // 2, 50), "AUTHORIZED OEM SERVICE ORDER & COMPONENT INSPECTION", fill=(191, 219, 254), font=f_small, anchor="mm")

    y = 90
    draw.text((35, y), f"SERVICE JOB NO: RO-{uuid.uuid4().hex[:6].upper()}", fill=(15, 23, 42), font=f_bold)
    draw.text((width - 35, y), f"SERVICE DATE: {rdate}", fill=(15, 23, 42), font=f_bold, anchor="ra")

    y += 24
    draw.line([(35, y), (width - 35, y)], fill=(203, 213, 225), width=1)

    y += 18
    draw.text((35, y), f"DEVICE: {product.product_name} ({product.brand} {product.model_number})", fill=(15, 23, 42), font=f_bold)
    y += 22
    draw.text((35, y), f"CHASSIS S/N: {product.serial_number}", fill=(30, 58, 138), font=f_mono)

    y += 28
    draw.rectangle([(35, y), (width - 35, y + 60)], fill=(241, 245, 249), outline=(203, 213, 225), width=1)
    draw.text((45, y + 18), "PARTS REPLACED: OEM Calibrated Board & Sub-assembly", fill=(15, 23, 42), font=f_norm)
    draw.text((45, y + 38), "OUTCOME: COMPLETE & FACTORY SPECIFIED", fill=(22, 163, 74), font=f_bold)

    y += 85
    draw.text((35, y), "TECHNICIAN SIGN-OFF: CERTIFIED OEM SPECIALIST", fill=(71, 85, 105), font=f_small)
    draw.text((width - 35, y), "STATUS: AUTHORIZED REPAIR ✓", fill=(22, 163, 74), font=f_bold, anchor="ra")

    file_name = f"repair_report_{uuid.uuid4().hex[:8]}.png"
    file_path = os.path.join(out_dir, file_name)
    img.save(file_path, "PNG")

    file_hash = _compute_sha256(file_path)
    file_size = os.path.getsize(file_path)

    doc = Document(
        user_id=product.user_id,
        product_id=product.product_id,
        claim_id=claim.claim_id if claim else None,
        doc_type='repair_report',
        file_name=file_name,
        file_path=file_path,
        file_hash=file_hash,
        file_size=file_size,
        mime_type='image/png',
        ocr_extracted_data={'repair_center': center, 'repair_date': rdate, 'serial_number': product.serial_number},
        ocr_status='completed'
    )
    db.session.add(doc)
    db.session.commit()
    return doc


# ── 5. COMPREHENSIVE POLICY ARTIFACTS ORCHESTRATOR ──────────────────────────

def generate_policy_artifacts_for_product(
    product_id: str,
    admin_user_id: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Orchestrates generation of all required policy documents for a registered product:
    - Receipt / Invoice
    - Warranty Certificate Card
    - Hardware Defect / Diagnostic Evidence
    - Repair Report (if automotive or requested)
    """
    admin_user_id = admin_user_id or user_id

    options = options or {}
    product = Product.query.get(product_id)
    if not product:
        raise ValueError(f"Product #{product_id} not found.")

    warranty = product.warranties.first()
    if not warranty:
        # Create standard warranty if missing
        from datetime import timedelta
        warranty = Warranty(
            product_id=product.product_id,
            warranty_type='standard',
            provider=f"{product.brand} Direct",
            start_date=product.purchase_date,
            expiry_date=product.purchase_date + timedelta(days=product.warranty_duration_months * 30),
            alert_days_before=30,
        )
        db.session.add(warranty)
        db.session.commit()

    created_docs = []

    # 1. Receipt
    if options.get('generate_receipt', True):
        doc_rec = generate_receipt_artifact(product)
        created_docs.append(doc_rec.to_dict())

    # 2. Warranty Card
    if options.get('generate_warranty_card', True):
        doc_wty = generate_warranty_card_artifact(product, warranty)
        created_docs.append(doc_wty.to_dict())

    # 3. Defect Evidence
    if options.get('generate_fault_evidence', True):
        doc_fault = generate_fault_evidence_artifact(
            product,
            damage_type=options.get('damage_type', 'electrical_failure'),
            fault_description=options.get('fault_description', 'Diagnostic telemetry confirms internal hardware failure under normal load.')
        )
        created_docs.append(doc_fault.to_dict())

    # 4. Repair report if automotive or requested
    if options.get('generate_repair_report', False) or product.category == 'automotive':
        doc_rep = generate_repair_report_artifact(product)
        created_docs.append(doc_rep.to_dict())

    if admin_user_id:
        log_action(
            user_id=admin_user_id,
            action_type='admin_generated_policy_artifacts',
            entity_type='product',
            entity_id=product_id,
            details={'documents_created': len(created_docs), 'category': product.category},
        )

    return {
        'product_id': product.product_id,
        'product_name': product.product_name,
        'category': product.category,
        'count': len(created_docs),
        'doc_types': [d['doc_type'] for d in created_docs],
        'documents': created_docs
    }

