"""
app/services/contradiction_detector.py
Cross-field consistency and anomaly detector (FR xxviii).
Discovers date contradictions, OCR mismatches, unauthorized repairs, and excluded damages.
"""
from datetime import date
from typing import List, Dict, Any
from app.extensions import db
from app.models import Claim, Product, Warranty, Document, RepairHistory
from app.utils.date_utils import parse_date_flexible
from app.services.policy_service import load_policy


def detect_contradictions(claim_id: str) -> List[Dict[str, Any]]:
    """
    Evaluates 8 cross-validation rules to detect internal contradictions:
    1. Claim submission date is before purchase date
    2. Fault date is in the future or after claim submission
    3. Fault date is before purchase date
    4. Receipt OCR purchase date differs significantly from registered purchase date
    5. Serial number in OCR differs from registered product serial number
    6. Model number in OCR differs from registered product model number
    7. Damage type is specifically excluded under category warranty policy
    8. Unauthorized repair history present when policy strictly requires authorized servicing
    """
    claim = Claim.query.get(claim_id)
    if not claim:
        return []

    product = Product.query.get(claim.product_id)
    warranty = Warranty.query.get(claim.warranty_id)
    docs = Document.query.filter_by(claim_id=claim_id).all()
    repairs = RepairHistory.query.filter_by(product_id=claim.product_id).all()

    policy = load_policy(product.category if product else 'general')
    contradictions = []

    sub_date = claim.claim_submission_date or date.today()
    fault_date = claim.fault_occurrence_date
    purch_date = product.purchase_date if product else None

    # 1. Claim date before purchase date
    if purch_date and sub_date < purch_date:
        contradictions.append({
            'code': 'C1_CLAIM_BEFORE_PURCHASE',
            'type': 'temporal_contradiction',
            'severity': 'high',
            'description': f"Claim submission date ({sub_date}) is prior to product purchase date ({purch_date})."
        })

    # 2. Fault date after claim submission
    if fault_date and fault_date > sub_date:
        contradictions.append({
            'code': 'C2_FAULT_AFTER_SUBMISSION',
            'type': 'temporal_contradiction',
            'severity': 'high',
            'description': f"Fault date ({fault_date}) cannot occur after claim submission date ({sub_date})."
        })

    # 3. Fault date before purchase date
    if purch_date and fault_date and fault_date < purch_date:
        contradictions.append({
            'code': 'C3_FAULT_BEFORE_PURCHASE',
            'type': 'temporal_contradiction',
            'severity': 'high',
            'description': f"Fault date ({fault_date}) is prior to product purchase date ({purch_date})."
        })

    # 4. OCR vs Registered Purchase Date
    for doc in docs:
        if doc.ocr_extracted_data and isinstance(doc.ocr_extracted_data, dict):
            ocr_date_str = doc.ocr_extracted_data.get('purchase_date')
            if ocr_date_str and purch_date:
                try:
                    ocr_date = parse_date_flexible(ocr_date_str)
                    diff_days = abs((ocr_date - purch_date).days)
                    if diff_days > 7:
                        contradictions.append({
                            'code': 'C4_OCR_DATE_MISMATCH',
                            'type': 'document_contradiction',
                            'severity': 'medium',
                            'description': f"Receipt purchase date ({ocr_date}) differs by {diff_days} days from registered purchase date ({purch_date})."
                        })
                except Exception:
                    pass

    # 5. OCR vs Registered Serial Number
    if product and product.serial_number:
        clean_reg_sn = product.serial_number.strip().upper()
        for doc in docs:
            if doc.ocr_extracted_data and isinstance(doc.ocr_extracted_data, dict):
                ocr_sn = doc.ocr_extracted_data.get('serial_number')
                if ocr_sn:
                    clean_ocr_sn = str(ocr_sn).strip().upper()
                    if clean_ocr_sn != clean_reg_sn and clean_ocr_sn not in clean_reg_sn and clean_reg_sn not in clean_ocr_sn:
                        contradictions.append({
                            'code': 'C5_OCR_SERIAL_MISMATCH',
                            'type': 'identity_contradiction',
                            'severity': 'high',
                            'description': f"Document serial number '{clean_ocr_sn}' does not match registered product serial number '{clean_reg_sn}'."
                        })

    # 6. OCR vs Registered Model Number
    if product and product.model_number:
        clean_reg_mod = product.model_number.strip().upper()
        for doc in docs:
            if doc.ocr_extracted_data and isinstance(doc.ocr_extracted_data, dict):
                ocr_mod = doc.ocr_extracted_data.get('model_number')
                if ocr_mod:
                    clean_ocr_mod = str(ocr_mod).strip().upper()
                    if clean_ocr_mod != clean_reg_mod and clean_ocr_mod not in clean_reg_mod and clean_reg_mod not in clean_ocr_mod:
                        contradictions.append({
                            'code': 'C6_OCR_MODEL_MISMATCH',
                            'type': 'identity_contradiction',
                            'severity': 'medium',
                            'description': f"Document model number '{clean_ocr_mod}' does not match registered model '{clean_reg_mod}'."
                        })

    # 7. Excluded damage under category policy
    excluded_damages = policy.get('excluded_damage_types', [])
    if claim.damage_type and claim.damage_type in excluded_damages:
        contradictions.append({
            'code': 'C7_EXCLUDED_DAMAGE_TYPE',
            'type': 'policy_contradiction',
            'severity': 'high',
            'description': f"Damage type '{claim.damage_type}' is explicitly excluded under {policy.get('category_name', product.category)} warranty policy."
        })

    # 8. Unauthorized repair history when policy requires authorized service
    if policy.get('requires_authorized_repair_only', True) and repairs:
        unauthorized = [r for r in repairs if not r.is_authorized]
        if unauthorized:
            contradictions.append({
                'code': 'C8_UNAUTHORIZED_REPAIR_HISTORY',
                'type': 'repair_contradiction',
                'severity': 'high',
                'description': f"Found {len(unauthorized)} unauthorized repair(s) in history, violating authorized service warranty terms."
            })

    # Update contradiction count on claim record
    claim.contradiction_count = len(contradictions)
    db.session.commit()

    return contradictions
