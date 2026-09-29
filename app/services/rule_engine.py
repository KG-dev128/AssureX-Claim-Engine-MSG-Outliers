"""
app/services/rule_engine.py
Deterministic 14-rule warranty validation engine (FR xxv).
Evaluates business constraints, document completeness, policy compliance, and chronological soundness.
Persists every rule result to rule_validation_results table.
"""
from datetime import date
from typing import Dict, Any, List
from app.extensions import db
from app.models import (
    Claim,
    Product,
    Warranty,
    Document,
    RepairHistory,
    RuleValidationResult,
)
from app.utils.date_utils import is_within_reporting_period
from app.services.policy_service import load_policy
from app.services.duplicate_detector import detect_duplicate_claim
from app.services.contradiction_detector import detect_contradictions


def evaluate_warranty_rules(claim_id: str) -> Dict[str, Any]:
    """
    Evaluates all 14 business rules for a claim:
    R1: Warranty Active (Fault occurred before warranty expiry)
    R2: Timely Reporting (Fault reported within max reporting days)
    R3: Product Age Validity (Purchase date to fault date within duration)
    R4: Damage Type Covered (Not in policy exclusion list)
    R5: Proof of Purchase (Receipt or invoice uploaded)
    R6: Fault Evidence Provided (Image or document showing fault)
    R7: Serial Number Registered (Non-empty serial number)
    R8: Serial Number Verified (Matches OCR when available)
    R9: Authorized Repairs (All prior repairs performed by authorized center)
    R10: Repair Count Within Limit (Prior repairs <= policy limit)
    R11: Prior Replacement Term (Checks terms if previous replacement occurred)
    R12: Deduplication Check (No duplicate invoice, file hash, or rapid repeat)
    R13: Chronological Soundness (No temporal contradictions)
    R14: Mandatory Documents Present (All required docs uploaded)
    """
    claim = Claim.query.get(claim_id)
    if not claim:
        raise ValueError(f"Claim #{claim_id} not found.")

    product = Product.query.get(claim.product_id)
    warranty = Warranty.query.get(claim.warranty_id)
    docs = Document.query.filter_by(claim_id=claim_id).all()
    repairs = RepairHistory.query.filter_by(product_id=claim.product_id).all()
    policy = load_policy(product.category if product else 'general')

    # Run auxiliary detectors first
    dup_res = detect_duplicate_claim(claim_id)
    contradictions = detect_contradictions(claim_id)

    doc_types = [d.doc_type for d in docs]
    required_docs = policy.get('required_documents', ['receipt', 'fault_evidence'])

    def is_required_doc_satisfied(req_doc: str, available_types: list) -> bool:
        if req_doc == 'receipt':
            return any(dt in ['receipt', 'invoice', 'proof_of_purchase'] for dt in available_types)
        elif req_doc == 'fault_evidence':
            return any(dt in ['fault_evidence', 'evidence', 'repair_report', 'diagnostic_log'] for dt in available_types)
        elif req_doc == 'product_image':
            return any(dt in ['product_image', 'serial_photo', 'product_photo'] for dt in available_types)
        return req_doc in available_types

    missing_docs = [rd for rd in required_docs if not is_required_doc_satisfied(rd, doc_types)]
    claim.missing_doc_count = len(missing_docs)

    rules = []

    # ─────────────────────────────────────────────────────────────────────────
    # R1: Warranty Active
    # ─────────────────────────────────────────────────────────────────────────
    r1_passed = bool(warranty and claim.fault_occurrence_date <= warranty.expiry_date)
    rules.append({
        'rule_name': 'R1_WARRANTY_ACTIVE',
        'rule_passed': r1_passed,
        'details': f"Fault date ({claim.fault_occurrence_date}) <= Expiry ({warranty.expiry_date if warranty else 'N/A'})"
    })

    # ─────────────────────────────────────────────────────────────────────────
    # R2: Timely Reporting
    # ─────────────────────────────────────────────────────────────────────────
    max_days = policy.get('max_claim_reporting_days', 30)
    sub_date = claim.claim_submission_date or date.today()
    r2_passed = is_within_reporting_period(claim.fault_occurrence_date, sub_date, max_days=max_days)
    rules.append({
        'rule_name': 'R2_TIMELY_REPORTING',
        'rule_passed': r2_passed,
        'details': f"Claim filed within {max_days} days of fault occurrence."
    })

    # ─────────────────────────────────────────────────────────────────────────
    # R3: Product Age Validity
    # ─────────────────────────────────────────────────────────────────────────
    duration_days = (product.warranty_duration_months or 12) * 31
    fault_age = (claim.fault_occurrence_date - product.purchase_date).days if product else 0
    r3_passed = fault_age >= 0 and fault_age <= duration_days
    rules.append({
        'rule_name': 'R3_PRODUCT_AGE_VALIDITY',
        'rule_passed': r3_passed,
        'details': f"Fault occurred at day {fault_age} (max allowable: {duration_days} days)."
    })

    # ─────────────────────────────────────────────────────────────────────────
    # R4: Damage Type Covered
    # ─────────────────────────────────────────────────────────────────────────
    excluded_damages = policy.get('excluded_damage_types', [])
    r4_passed = claim.damage_type not in excluded_damages if claim.damage_type else True
    rules.append({
        'rule_name': 'R4_DAMAGE_TYPE_COVERED',
        'rule_passed': r4_passed,
        'details': f"Damage type '{claim.damage_type}' not in policy exclusions: {excluded_damages}"
    })

    # ─────────────────────────────────────────────────────────────────────────
    # R5: Proof of Purchase Present
    # ─────────────────────────────────────────────────────────────────────────
    r5_passed = any(dt in ['receipt', 'invoice'] for dt in doc_types)
    rules.append({
        'rule_name': 'R5_PROOF_OF_PURCHASE',
        'rule_passed': r5_passed,
        'details': "Purchase receipt or invoice attached to claim."
    })

    # ─────────────────────────────────────────────────────────────────────────
    # R6: Fault Evidence Provided
    # ─────────────────────────────────────────────────────────────────────────
    r6_passed = any(dt in ['fault_evidence', 'product_image', 'repair_report'] for dt in doc_types)
    rules.append({
        'rule_name': 'R6_FAULT_EVIDENCE_PROVIDED',
        'rule_passed': r6_passed,
        'details': "Photographic or technical evidence of failure attached."
    })

    # ─────────────────────────────────────────────────────────────────────────
    # R7: Serial Number Registered
    # ─────────────────────────────────────────────────────────────────────────
    r7_passed = bool(product and product.serial_number and len(product.serial_number.strip()) >= 3)
    rules.append({
        'rule_name': 'R7_SERIAL_NUMBER_REGISTERED',
        'rule_passed': r7_passed,
        'details': f"Product serial number: {product.serial_number if product else 'None'}"
    })

    # ─────────────────────────────────────────────────────────────────────────
    # R8: Serial Number Verified
    # ─────────────────────────────────────────────────────────────────────────
    has_serial_contradiction = any(c['code'] == 'C5_OCR_SERIAL_MISMATCH' for c in contradictions)
    r8_passed = not has_serial_contradiction
    rules.append({
        'rule_name': 'R8_SERIAL_NUMBER_VERIFIED',
        'rule_passed': r8_passed,
        'details': "No contradiction between OCR document serial numbers and product serial number."
    })

    # ─────────────────────────────────────────────────────────────────────────
    # R9: Authorized Repairs
    # ─────────────────────────────────────────────────────────────────────────
    unauthorized = [r for r in repairs if not r.is_authorized]
    r9_passed = len(unauthorized) == 0
    rules.append({
        'rule_name': 'R9_AUTHORIZED_REPAIRS',
        'rule_passed': r9_passed,
        'details': f"{len(repairs)} previous repair(s); {len(unauthorized)} unauthorized."
    })

    # ─────────────────────────────────────────────────────────────────────────
    # R10: Repair Count Within Limit
    # ─────────────────────────────────────────────────────────────────────────
    max_repairs = policy.get('max_allowable_repairs', 3)
    r10_passed = len(repairs) <= max_repairs
    rules.append({
        'rule_name': 'R10_REPAIR_COUNT_LIMIT',
        'rule_passed': r10_passed,
        'details': f"Total repair count {len(repairs)} <= max limit {max_repairs}."
    })

    # ─────────────────────────────────────────────────────────────────────────
    # R11: Prior Replacement Term
    # ─────────────────────────────────────────────────────────────────────────
    # If previously replaced, check if warranty conditions allow second claim
    r11_passed = not (claim.previous_replacement and len(repairs) > 2)
    rules.append({
        'rule_name': 'R11_PRIOR_REPLACEMENT_TERM',
        'rule_passed': r11_passed,
        'details': f"Previous replacement flag: {claim.previous_replacement}."
    })

    # ─────────────────────────────────────────────────────────────────────────
    # R12: Deduplication Check
    # ─────────────────────────────────────────────────────────────────────────
    r12_passed = not dup_res['is_duplicate']
    rules.append({
        'rule_name': 'R12_DEDUPLICATION_CHECK',
        'rule_passed': r12_passed,
        'details': "No matching duplicate claims, hashes, or rapid filings found." if r12_passed else "; ".join(dup_res['reasons'])
    })

    # ─────────────────────────────────────────────────────────────────────────
    # R13: Chronological Soundness
    # ─────────────────────────────────────────────────────────────────────────
    temporal_contradictions = [c for c in contradictions if c['type'] == 'temporal_contradiction']
    r13_passed = len(temporal_contradictions) == 0
    rules.append({
        'rule_name': 'R13_CHRONOLOGICAL_SOUNDNESS',
        'rule_passed': r13_passed,
        'details': "All claim dates are coherent." if r13_passed else "; ".join([c['description'] for c in temporal_contradictions])
    })

    # ─────────────────────────────────────────────────────────────────────────
    # R14: Mandatory Documents Complete
    # ─────────────────────────────────────────────────────────────────────────
    r14_passed = len(missing_docs) == 0
    rules.append({
        'rule_name': 'R14_MANDATORY_DOCUMENTS_COMPLETE',
        'rule_passed': r14_passed,
        'details': "All required policy documents present." if r14_passed else f"Missing: {', '.join(missing_docs)}"
    })

    # ─────────────────────────────────────────────────────────────────────────
    # Persist Rule Validation Results in Database
    # ─────────────────────────────────────────────────────────────────────────
    # Remove existing results for this claim before re-evaluating
    RuleValidationResult.query.filter_by(claim_id=claim_id).delete()

    passed_count = 0
    failed_count = 0

    for r in rules:
        res_record = RuleValidationResult(
            claim_id=claim_id,
            rule_name=r['rule_name'],
            rule_passed=r['rule_passed'],
            details=r['details']
        )
        db.session.add(res_record)
        if r['rule_passed']:
            passed_count += 1
        else:
            failed_count += 1

    claim.warranty_conditions_met = (failed_count == 0)
    db.session.commit()

    return {
        'all_passed': failed_count == 0,
        'passed_count': passed_count,
        'failed_count': failed_count,
        'missing_documents': missing_docs,
        'contradictions': contradictions,
        'is_duplicate': dup_res['is_duplicate'],
        'results': rules,
    }
