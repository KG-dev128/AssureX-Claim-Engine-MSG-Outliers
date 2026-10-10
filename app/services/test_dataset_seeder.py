"""
app/services/test_dataset_seeder.py
Comprehensive testing dataset generator:
1. Product catalog across all 4 categories (Electronics, Appliances, Automotive, General)
2. Synthetic optical Receipts, Warranty Cards, and Proof images as per policies
3. Pre-evaluated claims for Valid, Invalid, and Manual Review classes
4. Updates CSV training/test dataset files
"""
import os
import uuid
import csv
import random
from datetime import datetime, date, timedelta
from typing import Dict, Any, List

from app.extensions import db
from app.models import (
    User, UserProfile, Product, Warranty, Claim, Document,
    RepairHistory, ClaimDecision, RuleValidationResult, AnomalyAlert
)
from app.services.auth_service import hash_password
from app.services.policy_service import seed_default_policies, load_policy
from app.services.document_artifact_generator import (
    generate_receipt_artifact,
    generate_warranty_card_artifact,
    generate_fault_evidence_artifact,
    generate_repair_report_artifact,
    generate_policy_artifacts_for_product
)
from app.services.card_generator import generate_claim_summary_card
from app.services.rule_engine import evaluate_warranty_rules
from app.services.ml_service import predict_claim
from app.services.gtm_service import predict_gtm
from app.services.decision_engine import evaluate_final_decision


PRODUCT_DEFINITIONS = [
    # ── Electronics (Category: electronics) ──
    {
        "category": "electronics",
        "brand": "Apple",
        "product_name": "iPhone 15 Pro Max 256GB",
        "model_number": "A3102",
        "serial_number": "SN-APPL-IP15P-88219",
        "purchase_price": 1199.00,
        "retailer": "Apple Fifth Avenue",
        "warranty_duration_months": 12,
        "days_ago": 60,
    },
    {
        "category": "electronics",
        "brand": "Apple",
        "product_name": "MacBook Pro 16-inch M3 Max",
        "model_number": "A2991",
        "serial_number": "SN-APPL-MBP16-99312",
        "purchase_price": 3499.00,
        "retailer": "Apple Regent Street",
        "warranty_duration_months": 12,
        "days_ago": 90,
    },
    {
        "category": "electronics",
        "brand": "Samsung",
        "product_name": "Galaxy S24 Ultra 512GB Titanium",
        "model_number": "SM-S928B",
        "serial_number": "SN-SMSG-S24U-44102",
        "purchase_price": 1299.00,
        "retailer": "Samsung Experience Store",
        "warranty_duration_months": 12,
        "days_ago": 45,
    },
    {
        "category": "electronics",
        "brand": "Sony",
        "product_name": "Sony WH-1000XM5 Noise-Canceling Headphones",
        "model_number": "WH1000XM5",
        "serial_number": "SN-SONY-XM5-77314",
        "purchase_price": 399.00,
        "retailer": "Best Buy Electronics Hub #402",
        "warranty_duration_months": 12,
        "days_ago": 80,
    },
    {
        "category": "electronics",
        "brand": "Dell",
        "product_name": "Dell XPS 15 9530 OLED Touch",
        "model_number": "XPS9530",
        "serial_number": "SN-DELL-XPS15-55192",
        "purchase_price": 2199.00,
        "retailer": "B&H Photo Video New York",
        "warranty_duration_months": 12,
        "days_ago": 110,
    },

    # ── Appliances (Category: appliances) ──
    {
        "category": "appliances",
        "brand": "Samsung",
        "product_name": "Samsung Bespoke 4-Door French Door Refrigerator",
        "model_number": "RF29BB8600",
        "serial_number": "SN-SMSG-FRDG-22819",
        "purchase_price": 2499.00,
        "retailer": "The Home Depot Appliances Center",
        "warranty_duration_months": 24,
        "days_ago": 180,
    },
    {
        "category": "appliances",
        "brand": "LG",
        "product_name": "LG AI DD 12kg Front Load Washer",
        "model_number": "F4V909WTS",
        "serial_number": "SN-LGE-WASH-66301",
        "purchase_price": 999.00,
        "retailer": "Currys PC World London",
        "warranty_duration_months": 24,
        "days_ago": 820,  # Expired warranty beyond grace period!
    },
    {
        "category": "appliances",
        "brand": "Dyson",
        "product_name": "Dyson V15 Detect Absolute Cordless Vacuum",
        "model_number": "V15-SV22",
        "serial_number": "SN-DYSN-V15-33190",
        "purchase_price": 749.00,
        "retailer": "Dyson Demo Store Oxford Street",
        "warranty_duration_months": 24,
        "days_ago": 150,
    },
    {
        "category": "appliances",
        "brand": "Bosch",
        "product_name": "Bosch Serie 6 Built-in Quiet Dishwasher",
        "model_number": "SMS6EDI06E",
        "serial_number": "SN-BSCH-DISH-99412",
        "purchase_price": 899.00,
        "retailer": "Lowe's Home Improvement #112",
        "warranty_duration_months": 24,
        "days_ago": 730,  # Tricky boundary date!
    },

    # ── Automotive (Category: automotive) ──
    {
        "category": "automotive",
        "brand": "Tesla",
        "product_name": "Tesla Wall Connector Gen 3 48A",
        "model_number": "1529455-02-D",
        "serial_number": "SN-TSLA-WC3-11928",
        "purchase_price": 475.00,
        "retailer": "Tesla Direct Online Store",
        "warranty_duration_months": 36,
        "days_ago": 140,
    },
    {
        "category": "automotive",
        "brand": "Nextbase",
        "product_name": "Nextbase 622GW 4K Ultra Dash Camera",
        "model_number": "NBDVR622GW",
        "serial_number": "SN-NXTB-622-44192",
        "purchase_price": 399.00,
        "retailer": "Halfords Auto Center UK",
        "warranty_duration_months": 36,
        "days_ago": 200,
    },
    {
        "category": "automotive",
        "brand": "NOCO",
        "product_name": "NOCO Boost Plus GB40 1000A Jump Starter",
        "model_number": "GB40",
        "serial_number": "SN-NOCO-GB40-88310",
        "purchase_price": 125.00,
        "retailer": "AutoZone Superstore #541",
        "warranty_duration_months": 36,
        "days_ago": 300,
    },
    {
        "category": "automotive",
        "brand": "Autel",
        "product_name": "Autel MaxiCOM MK808S OBD-II Diagnostic Tool",
        "model_number": "MK808S",
        "serial_number": "SN-AUTL-MK8-55201",
        "purchase_price": 499.00,
        "retailer": "O'Reilly Auto Parts Center",
        "warranty_duration_months": 36,
        "days_ago": 250,
    },

    # ── General (Category: general) ──
    {
        "category": "general",
        "brand": "DeWalt",
        "product_name": "DeWalt 20V MAX XR Brushless Compact Drill Kit",
        "model_number": "DCD805D2",
        "serial_number": "SN-DWLT-XR20-11029",
        "purchase_price": 229.00,
        "retailer": "Grainger Industrial Supply",
        "warranty_duration_months": 12,
        "days_ago": 40,
    },
    {
        "category": "general",
        "brand": "Sony",
        "product_name": "Sony Alpha 7 IV Full-Frame Mirrorless Camera",
        "model_number": "ILCE-7M4",
        "serial_number": "SN-SONY-A7IV-99381",
        "purchase_price": 2498.00,
        "retailer": "Adorama Camera New York",
        "warranty_duration_months": 12,
        "days_ago": 70,
    },
    {
        "category": "general",
        "brand": "Philips",
        "product_name": "Philips Hue Smart Hub & Ambient Starter Kit",
        "model_number": "3241312018",
        "serial_number": "SN-PHLP-HUE-66291",
        "purchase_price": 199.00,
        "retailer": "Target Electronics Express",
        "warranty_duration_months": 12,
        "days_ago": 130,
    },
    {
        "category": "general",
        "brand": "DJI",
        "product_name": "DJI Mini 4 Pro Drone Fly More Combo",
        "model_number": "MT4SSWD",
        "serial_number": "SN-DJI-MN4P-33198",
        "purchase_price": 1099.00,
        "retailer": "DJI Authorized Store San Francisco",
        "warranty_duration_months": 12,
        "days_ago": 55,
    }
]


def seed_test_users() -> Dict[str, User]:
    """Ensure standard test users for all 4 roles exist."""
    users_data = [
        ("customer@assurex.com", "customer_demo", "Customer User", "customer", "Customer123!"),
        ("reviewer@assurex.com", "reviewer_demo", "Senior Adjudicator", "reviewer", "Reviewer123!"),
        ("technician@assurex.com", "technician_demo", "Lead Service Technician", "service_employee", "Technician123!"),
        ("admin@assurex.com", "admin", "System Administrator", "admin", "Admin123!"),
    ]
    created = {}
    for email, uname, fname, role, pw in users_data:
        u = User.query.filter((User.email == email) | (User.username == uname)).first()
        if not u:
            u = User(
                username=uname,
                email=email,
                password_hash=hash_password(pw),
                role=role,
                is_active=True,
            )
            db.session.add(u)
            db.session.flush()
            prof = UserProfile(
                user_id=u.user_id,
                full_name=fname,
                phone="+1 (555) 019-2834",
                address="AssureX Enterprise Campus, Building 4",
                organization="AssureX Warranty Solutions"
            )
            db.session.add(prof)
        else:
            u.role = role
            u.is_active = True
        created[role] = u
    db.session.commit()
    return created


def seed_product_catalog(customer_user: User) -> List[Product]:
    """Seed comprehensive catalog across all 4 policy categories with generated documents."""
    products = []
    today = date.today()

    for pdef in PRODUCT_DEFINITIONS:
        p = Product.query.filter_by(serial_number=pdef['serial_number']).first()
        pdate = today - timedelta(days=pdef['days_ago'])

        if not p:
            p = Product(
                user_id=customer_user.user_id,
                product_name=pdef['product_name'],
                category=pdef['category'],
                brand=pdef['brand'],
                model_number=pdef['model_number'],
                serial_number=pdef['serial_number'],
                purchase_date=pdate,
                purchase_price=pdef['purchase_price'],
                retailer=pdef['retailer'],
                warranty_duration_months=pdef['warranty_duration_months'],
            )
            db.session.add(p)
            db.session.flush()

            # Create warranty
            wty_days = pdef['warranty_duration_months'] * 30
            w = Warranty(
                product_id=p.product_id,
                warranty_type='standard',
                provider=f"{p.brand} Direct OEM",
                start_date=pdate,
                expiry_date=pdate + timedelta(days=wty_days),
                alert_days_before=30,
            )
            db.session.add(w)
            db.session.commit()

            # Automatically generate policy artifacts (Receipt & Warranty Card)
            generate_policy_artifacts_for_product(
                p.product_id,
                admin_user_id=customer_user.user_id,
                options={'generate_receipt': True, 'generate_warranty_card': True, 'generate_fault_evidence': False}
            )
        products.append(p)

    return products


def _execute_full_claim_evaluation(claim: Claim):
    """Executes the dual-model inference and 14 rules for a created claim."""
    claim.status = 'under_evaluation'
    db.session.commit()

    card_path = generate_claim_summary_card(claim.claim_id)
    rule_results = evaluate_warranty_rules(claim.claim_id)
    py_pred = predict_claim(claim.claim_id)
    gtm_pred = predict_gtm(claim.claim_id, card_path)
    final_res = evaluate_final_decision(claim.claim_id, py_pred, gtm_pred, rule_results)
    return final_res


def seed_test_claims(customer_user: User, products: List[Product]) -> Dict[str, List[Claim]]:
    """
    Creates and evaluates a rich set of claims for each outcome class:
    - Valid Claims (Likely Valid)
    - Invalid Claims (Likely Invalid)
    - Manual Review Claims (Manual Review Required)
    """
    today = date.today()
    prod_map = {p.serial_number: p for p in products}

    results = {'valid': [], 'invalid': [], 'manual_review': []}

    # Helper to check if claim already seeded
    def find_or_create_claim(p: Product, damage_type: str, fdate: date, desc: str, prev_rep: bool = False) -> Claim:
        existing = Claim.query.filter_by(product_id=p.product_id, damage_type=damage_type).first()
        if existing:
            return existing

        w = p.warranties.first()
        c = Claim(
            user_id=customer_user.user_id,
            product_id=p.product_id,
            warranty_id=w.warranty_id if w else None,
            product_age_days=(fdate - p.purchase_date).days,
            fault_occurrence_date=fdate,
            fault_description=desc,
            damage_type=damage_type,
            previous_replacement=prev_rep,
            status='submitted',
            claim_submission_date=today
        )
        db.session.add(c)
        db.session.commit()
        return c

    # ══════════════════════════════════════════════════════════════════════════
    # 1. VALID CLAIMS (Likely Valid / Approved)
    # ══════════════════════════════════════════════════════════════════════════

    # Valid 1: Electronics - iPhone 15 Pro (battery/charging port power failure)
    p_ip15 = prod_map.get("SN-APPL-IP15P-88219")
    if p_ip15:
        c1 = find_or_create_claim(
            p_ip15,
            damage_type="electrical_failure",
            fdate=today - timedelta(days=5),
            desc="USB-C power rail controller failed; device refuses to accept charging current under normal temperature."
        )
        # Ensure Receipt and Defect Evidence attached
        generate_receipt_artifact(p_ip15, claim=c1)
        generate_fault_evidence_artifact(p_ip15, claim=c1, damage_type="electrical_failure", fault_description=c1.fault_description)
        _execute_full_claim_evaluation(c1)
        results['valid'].append(c1)

    # Valid 2: Appliances - Samsung French Door Refrigerator (cooling system valve)
    p_fridge = prod_map.get("SN-SMSG-FRDG-22819")
    if p_fridge:
        c2 = find_or_create_claim(
            p_fridge,
            damage_type="cooling_system_failure",
            fdate=today - timedelta(days=12),
            desc="Main twin-cooling solenoid valve failure; refrigerator compartment temperature exceeds 55F while freezer works."
        )
        generate_receipt_artifact(p_fridge, claim=c2)
        generate_fault_evidence_artifact(p_fridge, claim=c2, damage_type="cooling_system_failure", fault_description=c2.fault_description)
        _execute_full_claim_evaluation(c2)
        results['valid'].append(c2)

    # Valid 3: Automotive - Tesla Wall Connector (pilot pin control failure)
    p_tsla = prod_map.get("SN-TSLA-WC3-11928")
    if p_tsla:
        c3 = find_or_create_claim(
            p_tsla,
            damage_type="electrical_failure",
            fdate=today - timedelta(days=8),
            desc="Control pilot pin internal circuit open failure; Red blinking light indicates relay disconnect error."
        )
        generate_receipt_artifact(p_tsla, claim=c3)
        generate_repair_report_artifact(p_tsla, claim=c3)
        generate_fault_evidence_artifact(p_tsla, claim=c3, damage_type="electrical_failure", fault_description=c3.fault_description)
        _execute_full_claim_evaluation(c3)
        results['valid'].append(c3)

    # Valid 4: General - DeWalt 20V Drill (armature coil winding defect)
    p_dwlt = prod_map.get("SN-DWLT-XR20-11029")
    if p_dwlt:
        c4 = find_or_create_claim(
            p_dwlt,
            damage_type="mechanical_failure",
            fdate=today - timedelta(days=10),
            desc="Planetary gearbox chuck assembly seized under standard torque clutch setting #5."
        )
        generate_receipt_artifact(p_dwlt, claim=c4)
        generate_fault_evidence_artifact(p_dwlt, claim=c4, damage_type="mechanical_failure", fault_description=c4.fault_description)
        _execute_full_claim_evaluation(c4)
        results['valid'].append(c4)


    # ══════════════════════════════════════════════════════════════════════════
    # 2. INVALID CLAIMS (Likely Invalid / Rejected)
    # ══════════════════════════════════════════════════════════════════════════

    # Invalid 1: Electronics - MacBook Pro (Liquid immersion / water damage - Policy Exclusion)
    p_mbp = prod_map.get("SN-APPL-MBP16-99312")
    if p_mbp:
        c_inv1 = find_or_create_claim(
            p_mbp,
            damage_type="water_damage",
            fdate=today - timedelta(days=4),
            desc="Full liquid immersion in swimming pool; logic board has active corrosion and liquid contact indicators triggered."
        )
        generate_receipt_artifact(p_mbp, claim=c_inv1)
        generate_fault_evidence_artifact(p_mbp, claim=c_inv1, damage_type="water_damage", fault_description=c_inv1.fault_description)
        _execute_full_claim_evaluation(c_inv1)
        results['invalid'].append(c_inv1)

    # Invalid 2: Appliances - LG Front Load Washer (Expired Warranty past 730 days)
    p_wash = prod_map.get("SN-LGE-WASH-66301")
    if p_wash:
        c_inv2 = find_or_create_claim(
            p_wash,
            damage_type="mechanical_failure",
            fdate=today - timedelta(days=15),
            desc="Direct-drive rotor bearing noise reported 820 days after initial installation."
        )
        generate_receipt_artifact(p_wash, claim=c_inv2)
        generate_fault_evidence_artifact(p_wash, claim=c_inv2, damage_type="mechanical_failure", fault_description=c_inv2.fault_description)
        _execute_full_claim_evaluation(c_inv2)
        results['invalid'].append(c_inv2)

    # Invalid 3: Automotive - Nextbase Dashcam (Accident Collision - Policy Exclusion)
    p_nxt = prod_map.get("SN-NXTB-622-44192")
    if p_nxt:
        c_inv3 = find_or_create_claim(
            p_nxt,
            damage_type="accident_collision",
            fdate=today - timedelta(days=7),
            desc="Dashcam lens housing fractured during high-speed vehicle impact collision."
        )
        generate_receipt_artifact(p_nxt, claim=c_inv3)
        generate_fault_evidence_artifact(p_nxt, claim=c_inv3, damage_type="accident_collision", fault_description=c_inv3.fault_description)
        _execute_full_claim_evaluation(c_inv3)
        results['invalid'].append(c_inv3)

    # Invalid 4: General - Sony A7 IV (Duplicate Document SHA-256 reuse - Rule R12)
    p_a7 = prod_map.get("SN-SONY-A7IV-99381")
    if p_a7:
        c_inv4 = find_or_create_claim(
            p_a7,
            damage_type="screen_crack",
            fdate=today - timedelta(days=14),
            desc="Rear articulating LCD panel ribbon cable failure."
        )
        # Reuse existing receipt document to trigger duplicate hash detection
        existing_doc = Document.query.filter_by(doc_type='receipt').first()
        if existing_doc:
            dup_doc = Document(
                user_id=customer_user.user_id,
                product_id=p_a7.product_id,
                claim_id=c_inv4.claim_id,
                doc_type='receipt',
                file_name=existing_doc.file_name,
                file_path=existing_doc.file_path,
                file_hash=existing_doc.file_hash,  # IDENTICAL HASH
                file_size=existing_doc.file_size,
                mime_type='image/png',
                ocr_extracted_data=existing_doc.ocr_extracted_data,
                ocr_status='completed'
            )
            db.session.add(dup_doc)
            db.session.commit()
        generate_fault_evidence_artifact(p_a7, claim=c_inv4, damage_type="screen_crack", fault_description=c_inv4.fault_description)
        _execute_full_claim_evaluation(c_inv4)
        results['invalid'].append(c_inv4)

    # Invalid 5: Contradictory Chronology (Fault date 30 days before purchase - Rule R13)
    p_hue = prod_map.get("SN-PHLP-HUE-66291")
    if p_hue:
        c_inv5 = find_or_create_claim(
            p_hue,
            damage_type="electrical_failure",
            fdate=p_hue.purchase_date - timedelta(days=30),  # TEMPORAL CONTRADICTION
            desc="Zigbee bridge radio circuit stopped broadcasting beacons before the device was bought."
        )
        generate_receipt_artifact(p_hue, claim=c_inv5)
        generate_fault_evidence_artifact(p_hue, claim=c_inv5, damage_type="electrical_failure", fault_description=c_inv5.fault_description)
        _execute_full_claim_evaluation(c_inv5)
        results['invalid'].append(c_inv5)


    # ══════════════════════════════════════════════════════════════════════════
    # 3. MANUAL REVIEW CLAIMS (Manual Review Required)
    # ══════════════════════════════════════════════════════════════════════════

    # Manual Review 1: Model Disagreement - Sony WH-1000XM5
    p_xm5 = prod_map.get("SN-SONY-XM5-77314")
    if p_xm5:
        c_man1 = find_or_create_claim(
            p_xm5,
            damage_type="software_glitch",
            fdate=today - timedelta(days=6),
            desc="Intermittent Bluetooth codec disconnection under heavy 2.4GHz interference."
        )
        generate_receipt_artifact(p_xm5, claim=c_man1)
        generate_fault_evidence_artifact(p_xm5, claim=c_man1, damage_type="software_glitch", fault_description=c_man1.fault_description)
        _execute_full_claim_evaluation(c_man1)
        results['manual_review'].append(c_man1)

    # Manual Review 2: Missing Required Proof of Purchase Document (Rule R5 & R14)
    p_dysn = prod_map.get("SN-DYSN-V15-33190")
    if p_dysn:
        c_man2 = find_or_create_claim(
            p_dysn,
            damage_type="mechanical_failure",
            fdate=today - timedelta(days=9),
            desc="High-torque cleaner head bearing vibration. Customer misplaced paper store receipt."
        )
        # OMIT RECEIPT - only attach fault evidence
        generate_fault_evidence_artifact(p_dysn, claim=c_man2, damage_type="mechanical_failure", fault_description=c_man2.fault_description)
        _execute_full_claim_evaluation(c_man2)
        results['manual_review'].append(c_man2)

    # Manual Review 3: Serial Number Mismatch (Rule R8)
    p_autl = prod_map.get("SN-AUTL-MK8-55201")
    if p_autl:
        c_man3 = find_or_create_claim(
            p_autl,
            damage_type="sensor_failure",
            fdate=today - timedelta(days=11),
            desc="OBD-II CAN bus transceiver IC communication timeout."
        )
        # Generate receipt with a DIFFERENT serial number to trigger R8 mismatch
        generate_receipt_artifact(p_autl, claim=c_man3, override_serial="SN-AUTL-MK8-MISMATCH-999")
        generate_fault_evidence_artifact(p_autl, claim=c_man3, damage_type="sensor_failure", fault_description=c_man3.fault_description)
        _execute_full_claim_evaluation(c_man3)
        results['manual_review'].append(c_man3)

    # Manual Review 4: Prior Unauthorized Repair (Rule R9)
    p_noco = prod_map.get("SN-NOCO-GB40-88310")
    if p_noco:
        c_man4 = find_or_create_claim(
            p_noco,
            damage_type="electrical_failure",
            fdate=today - timedelta(days=13),
            desc="Lithium cell balance charging controller shutoff failure."
        )
        # Add unauthorized repair record
        rep = RepairHistory.query.filter_by(product_id=p_noco.product_id).first()
        if not rep:
            rep = RepairHistory(
                product_id=p_noco.product_id,
                claim_id=c_man4.claim_id,
                repair_date=today - timedelta(days=60),
                repair_center="Speedy Joe Non-OEM Unofficial Auto Repair",
                is_authorized=False,  # UNAUTHORIZED REPAIR
                replaced_parts="Non-certified bypass diode",
                repair_outcome="Partial",
                notes="Unauthorized casing opened by third-party technician."
            )
            db.session.add(rep)
            db.session.commit()
        generate_receipt_artifact(p_noco, claim=c_man4)
        generate_fault_evidence_artifact(p_noco, claim=c_man4, damage_type="electrical_failure", fault_description=c_man4.fault_description)
        _execute_full_claim_evaluation(c_man4)
        results['manual_review'].append(c_man4)

    # Manual Review 5: Tricky Boundary Date (Warranty grace threshold)
    p_bsch = prod_map.get("SN-BSCH-DISH-99412")
    if p_bsch:
        c_man5 = find_or_create_claim(
            p_bsch,
            damage_type="electrical_failure",
            fdate=today - timedelta(days=1),
            desc="Drain pump circulation impeller error code E24 on final day of statutory coverage."
        )
        generate_receipt_artifact(p_bsch, claim=c_man5)
        generate_fault_evidence_artifact(p_bsch, claim=c_man5, damage_type="electrical_failure", fault_description=c_man5.fault_description)
        _execute_full_claim_evaluation(c_man5)
        results['manual_review'].append(c_man5)

    return results


def sync_csv_dataset_with_categories():
    """
    Enriches the CSV dataset files in data/dataset/ to ensure exact representation
    of all 4 policy categories (Electronics, Appliances, Automotive, General)
    and balanced Valid, Invalid, Manual Review distributions.
    """
    dataset_dir = os.path.join('data', 'dataset')
    os.makedirs(dataset_dir, exist_ok=True)
    master_csv = os.path.join(dataset_dir, 'claims_master.csv')

    headers = [
        'claim_id', 'product_category', 'brand', 'product_age_days',
        'warranty_duration_days', 'remaining_warranty_days', 'is_warranty_active',
        'fault_category', 'damage_type', 'days_since_fault', 'repair_count',
        'is_authorized_repair', 'previous_replacement', 'has_purchase_receipt',
        'has_warranty_card', 'has_product_image', 'has_fault_evidence',
        'has_repair_report', 'serial_number_match', 'is_excluded_damage',
        'is_extended_warranty', 'missing_doc_count', 'contradiction_count',
        'is_duplicate', 'claim_amount', 'label'
    ]

    cats = [
        ('Electronics', ['Apple', 'Samsung', 'Sony', 'Dell', 'Lenovo']),
        ('Appliances', ['Samsung', 'LG', 'Dyson', 'Bosch', 'Whirlpool']),
        ('Automotive', ['Tesla', 'Nextbase', 'NOCO', 'Autel', 'Bosch']),
        ('General', ['DeWalt', 'Sony', 'Philips', 'DJI', 'Makita'])
    ]

    rows = []
    # Generate 1500 records: 500 valid, 500 invalid, 500 manual_review
    labels = ['valid'] * 500 + ['invalid'] * 500 + ['manual_review'] * 500
    random.seed(42)
    random.shuffle(labels)

    for i, label in enumerate(labels, 1):
        cid = f"CLM-{uuid.uuid4().hex[:5].upper()}-{uuid.uuid4().hex[:5].upper()}"
        cat_name, brands = random.choice(cats)
        brand = random.choice(brands)
        w_dur = random.choice([365, 730, 1095])

        if label == 'valid':
            age = random.randint(30, int(w_dur * 0.75))
            rem = w_dur - age
            active = 1
            days_fault = random.randint(2, 20)
            rep_count = random.choice([0, 1])
            auth_rep = 1
            has_rec = 1
            has_wty = 1
            has_ev = 1
            sn_match = 1
            excluded = 0
            missing = 0
            contra = 0
            dup = 0
            dmg = random.choice(['electrical_failure', 'mechanical_failure', 'software_glitch'])
        elif label == 'invalid':
            is_exp = random.random() < 0.35
            if is_exp:
                age = w_dur + random.randint(45, 120)
                rem = w_dur - age
                active = 0
            else:
                age = random.randint(30, int(w_dur * 0.8))
                rem = w_dur - age
                active = 1
            days_fault = random.randint(5, 45)
            rep_count = random.choice([0, 1, 2])
            auth_rep = random.choice([0, 1])
            has_rec = random.choice([0, 1])
            has_wty = random.choice([0, 1])
            has_ev = random.choice([0, 1])
            sn_match = random.choice([0, 1])
            excluded = 1 if not is_exp else random.choice([0, 1])
            missing = random.randint(1, 3) if has_rec == 0 else 0
            contra = 1 if random.random() < 0.25 else 0
            dup = 1 if random.random() < 0.2 else 0
            dmg = random.choice(['water_damage', 'pest_infestation', 'racing_usage', 'accident_collision', 'wear_and_tear'])
        else:  # manual_review
            age = random.randint(int(w_dur * 0.7), w_dur + 10)
            rem = w_dur - age
            active = 1 if rem >= -14 else 0
            days_fault = random.randint(15, 35)
            rep_count = random.choice([1, 2, 3])
            auth_rep = random.choice([0, 1])
            has_rec = random.choice([0, 1])
            has_wty = 1
            has_ev = 1
            sn_match = random.choice([0, 1])
            excluded = 0
            missing = 1 if has_rec == 0 else 0
            contra = 0
            dup = 0
            dmg = random.choice(['electrical_failure', 'manufacturing_defect', 'sensor_failure'])

        amount = round(random.uniform(120.0, 3950.0), 2)

        rows.append({
            'claim_id': cid,
            'product_category': cat_name,
            'brand': brand,
            'product_age_days': age,
            'warranty_duration_days': w_dur,
            'remaining_warranty_days': rem,
            'is_warranty_active': active,
            'fault_category': dmg,
            'damage_type': dmg,
            'days_since_fault': days_fault,
            'repair_count': rep_count,
            'is_authorized_repair': auth_rep,
            'previous_replacement': 1 if rep_count >= 2 else 0,
            'has_purchase_receipt': has_rec,
            'has_warranty_card': has_wty,
            'has_product_image': 1,
            'has_fault_evidence': has_ev,
            'has_repair_report': 1 if cat_name == 'Automotive' else 0,
            'serial_number_match': sn_match,
            'is_excluded_damage': excluded,
            'is_extended_warranty': 1 if w_dur > 365 else 0,
            'missing_doc_count': missing,
            'contradiction_count': contra,
            'is_duplicate': dup,
            'claim_amount': amount,
            'label': label
        })

    # Write Master CSV
    with open(master_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    # Stratified Splits: 1050 train (350/class), 225 val (75/class), 225 test (75/class)
    by_label = {'valid': [], 'invalid': [], 'manual_review': []}
    for r in rows:
        by_label[r['label']].append(r)

    train_rows = by_label['valid'][:350] + by_label['invalid'][:350] + by_label['manual_review'][:350]
    val_rows = by_label['valid'][350:425] + by_label['invalid'][350:425] + by_label['manual_review'][350:425]
    test_rows = by_label['valid'][425:500] + by_label['invalid'][425:500] + by_label['manual_review'][425:500]

    for split_name, s_rows in [('claims_train.csv', train_rows), ('claims_val.csv', val_rows), ('claims_test.csv', test_rows)]:
        s_path = os.path.join(dataset_dir, split_name)
        with open(s_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(s_rows)


def run_full_dataset_seeding() -> Dict[str, Any]:
    """Master seeding entry point callable from Python or Flask API."""
    seed_default_policies()
    users = seed_test_users()
    customer = users['customer']
    products = seed_product_catalog(customer)
    claims_dict = seed_test_claims(customer, products)
    sync_csv_dataset_with_categories()

    return {
        'status': 'success',
        'users_count': len(users),
        'products_count': len(products),
        'valid_claims_count': len(claims_dict['valid']),
        'invalid_claims_count': len(claims_dict['invalid']),
        'manual_review_claims_count': len(claims_dict['manual_review']),
        'total_claims_created': len(claims_dict['valid']) + len(claims_dict['invalid']) + len(claims_dict['manual_review']),
        'dataset_csv_updated': True
    }
