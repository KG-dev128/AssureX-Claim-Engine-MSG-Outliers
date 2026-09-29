"""
app/services/preprocessing_service.py
Feature engineering and claim vector transformation (FR xvi).
Extracts 22 numerical, categorical, and indicator features for ML inference.
"""
from datetime import date
from typing import Dict, Any, List, Optional
import numpy as np
from app.models import Claim, Product, Warranty, Document, RepairHistory
from app.services.policy_service import load_policy

FEATURE_COLUMNS = [
    'product_age_days',
    'remaining_warranty_days',
    'is_warranty_active',
    'warranty_utilization_pct',
    'days_since_fault',
    'product_category_idx',
    'damage_type_idx',
    'fault_category_idx',
    'repair_count',
    'is_authorized_repair',
    'previous_replacement',
    'has_purchase_receipt',
    'has_warranty_card',
    'has_product_image',
    'has_fault_evidence',
    'has_repair_report',
    'missing_doc_count',
    'contradiction_count',
    'is_duplicate',
    'serial_number_match',
    'is_excluded_damage',
    'is_extended_warranty',
]

CATEGORIES = ['electronics', 'appliances', 'automotive', 'general']
DAMAGE_TYPES = [
    'electrical_failure',
    'mechanical_failure',
    'screen_crack',
    'water_damage',
    'wear_and_tear',
    'battery_degradation',
    'software_glitch',
    'other',
]
FAULT_CATEGORIES = ['electrical', 'mechanical', 'physical', 'cosmetic', 'performance', 'unknown']


def classify_fault_text(description: str) -> str:
    """Keyword-based fault category classifier."""
    text = (description or '').lower()
    if any(k in text for k in ['spark', 'power', 'battery', 'charge', 'circuit', 'smoke', 'voltage', 'short']):
        return 'electrical'
    if any(k in text for k in ['motor', 'gear', 'grind', 'jam', 'bearing', 'pump', 'rattle']):
        return 'mechanical'
    if any(k in text for k in ['crack', 'drop', 'shatter', 'smash', 'dent', 'crushed', 'hinge']):
        return 'physical'
    if any(k in text for k in ['scratch', 'fade', 'peel', 'discolor', 'stain']):
        return 'cosmetic'
    if any(k in text for k in ['slow', 'freeze', 'hang', 'heat', 'drain', 'reboot', 'glitch']):
        return 'performance'
    return 'unknown'


def build_feature_dict(claim_id: str) -> Dict[str, Any]:
    """
    Constructs comprehensive raw feature dictionary from DB models.
    """
    claim = Claim.query.get(claim_id)
    if not claim:
        raise ValueError(f"Claim #{claim_id} not found.")

    product = Product.query.get(claim.product_id)
    warranty = Warranty.query.get(claim.warranty_id)
    docs = Document.query.filter_by(claim_id=claim_id).all()
    repairs = RepairHistory.query.filter_by(product_id=claim.product_id).all()
    policy = load_policy(product.category if product else 'general')

    today = date.today()
    purch_date = product.purchase_date if product else today
    fault_date = claim.fault_occurrence_date if claim.fault_occurrence_date else today
    exp_date = warranty.expiry_date if warranty else today

    product_age_days = max(0, (fault_date - purch_date).days)
    remaining_warranty_days = (exp_date - fault_date).days
    total_warranty_days = max(1, (exp_date - purch_date).days)
    warranty_utilization_pct = min(1.5, max(0.0, product_age_days / total_warranty_days))
    days_since_fault = max(0, (today - fault_date).days)

    doc_types = [d.doc_type for d in docs]
    excluded_damages = policy.get('excluded_damage_types', [])

    has_receipt = int(any(dt in ['receipt', 'invoice'] for dt in doc_types))
    has_card = int('warranty_card' in doc_types)
    has_image = int('product_image' in doc_types)
    has_evidence = int('fault_evidence' in doc_types)
    has_repair = int('repair_report' in doc_types)

    is_authorized = 1
    if repairs:
        is_authorized = int(all(r.is_authorized for r in repairs))

    category_slug = product.category.lower() if product else 'general'
    damage_slug = (claim.damage_type or 'other').lower()
    fault_cat = classify_fault_text(claim.fault_description)

    serial_match = 1
    # Check if any OCR serial mismatch contradiction exists
    if claim.contradiction_count > 0:
        for d in docs:
            if d.ocr_extracted_data and isinstance(d.ocr_extracted_data, dict):
                ocr_sn = d.ocr_extracted_data.get('serial_number')
                if ocr_sn and product and product.serial_number:
                    if str(ocr_sn).strip().upper() != product.serial_number.strip().upper():
                        serial_match = 0
                        break

    is_excluded = int(damage_slug in excluded_damages)
    is_ext_warranty = int(warranty.warranty_type == 'extended' if warranty else 0)

    cat_idx = CATEGORIES.index(category_slug) if category_slug in CATEGORIES else 3
    dmg_idx = DAMAGE_TYPES.index(damage_slug) if damage_slug in DAMAGE_TYPES else 7
    fault_idx = FAULT_CATEGORIES.index(fault_cat) if fault_cat in FAULT_CATEGORIES else 5

    features = {
        'product_age_days': float(product_age_days),
        'remaining_warranty_days': float(remaining_warranty_days),
        'is_warranty_active': float(1 if remaining_warranty_days >= 0 else 0),
        'warranty_utilization_pct': float(warranty_utilization_pct),
        'days_since_fault': float(days_since_fault),
        'product_category': category_slug,
        'product_category_idx': float(cat_idx),
        'damage_type': damage_slug,
        'damage_type_idx': float(dmg_idx),
        'fault_category': fault_cat,
        'fault_category_idx': float(fault_idx),
        'repair_count': float(len(repairs)),
        'is_authorized_repair': float(is_authorized),
        'previous_replacement': float(1 if claim.previous_replacement else 0),
        'has_purchase_receipt': float(has_receipt),
        'has_warranty_card': float(has_card),
        'has_product_image': float(has_image),
        'has_fault_evidence': float(has_evidence),
        'has_repair_report': float(has_repair),
        'missing_doc_count': float(claim.missing_doc_count),
        'contradiction_count': float(claim.contradiction_count),
        'is_duplicate': float(1 if claim.is_duplicate else 0),
        'serial_number_match': float(serial_match),
        'is_excluded_damage': float(is_excluded),
        'is_extended_warranty': float(is_ext_warranty),
        'claim_amount': float(product.purchase_price if product and product.purchase_price else 299.99),
    }

    return features


def build_feature_vector(claim_id: str) -> np.ndarray:
    """
    Produces normalized 1D numpy feature vector ready for ML model prediction.
    """
    f = build_feature_dict(claim_id)
    vector = [f[col] for col in FEATURE_COLUMNS]
    return np.array(vector, dtype=np.float32).reshape(1, -1)
