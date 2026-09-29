"""
app/services/decision_engine.py
Central synthesis and 3-class decision engine (FR xxxiv, xxxv).
Fuses Python model predictions, GTM visual predictions, rule outcomes, deduplication flags,
and contradiction counts into a decisive final classification with transparent explanation.
"""
from datetime import datetime
from typing import Dict, Any, Optional
from app.extensions import db
from app.models import Claim, ClaimDecision, ModelPrediction
from app.services.audit_service import log_action
from app.services.notification_service import notify_claim_status_change


def compute_consistency_status(
    py_class: str,
    py_conf: float,
    gtm_class: str,
    gtm_conf: float,
) -> str:
    """
    Determine consistency between dual AI models (Python tabular + GTM visual).
    Categories:
      - strong_match: identical class, |diff| <= 0.15
      - acceptable_match: identical class, |diff| <= 0.30
      - weak_match: identical class, |diff| > 0.30
      - model_disagreement: different predicted classes
      - uncertain_result: either confidence below 0.55
    """
    if py_conf < 0.55 or gtm_conf < 0.55:
        return 'uncertain_result'

    if py_class != gtm_class:
        return 'model_disagreement'

    diff = abs(py_conf - gtm_conf)
    if diff <= 0.15:
        return 'strong_match'
    elif diff <= 0.30:
        return 'acceptable_match'
    else:
        return 'weak_match'


def evaluate_final_decision(
    claim_id: str,
    python_pred: Dict[str, Any],
    gtm_pred: Optional[Dict[str, Any]],
    rule_results: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Executes holistic multi-tier decision matrix combining:
    - Python tabular model
    - GTM visual model (or fallback if visual model not yet engaged)
    - 14 business rules
    - Contradictions & duplicate checks

    Returns dictionary with decision metrics and saves ClaimDecision to database.
    """
    claim = Claim.query.get(claim_id)
    if not claim:
        raise ValueError(f"Claim #{claim_id} not found.")

    py_class = python_pred.get('predicted_class', 'manual_review')
    py_conf = max([
        float(python_pred.get('confidence_valid', 0.0) or 0.0),
        float(python_pred.get('confidence_invalid', 0.0) or 0.0),
        float(python_pred.get('confidence_manual_review', 0.0) or 0.0),
    ])

    if gtm_pred:
        gtm_class = gtm_pred.get('predicted_class', py_class)
        gtm_conf = max([
            float(gtm_pred.get('confidence_valid', 0.0) or 0.0),
            float(gtm_pred.get('confidence_invalid', 0.0) or 0.0),
            float(gtm_pred.get('confidence_manual_review', 0.0) or 0.0),
        ])
    else:
        # Default aligned fallback if GTM card inference pending
        gtm_class = py_class
        gtm_conf = py_conf

    conf_diff = round(abs(py_conf - gtm_conf), 4)
    consistency = compute_consistency_status(py_class, py_conf, gtm_class, gtm_conf)

    passed_count = rule_results.get('passed_count', 0)
    failed_count = rule_results.get('failed_count', 0)
    missing_docs = rule_results.get('missing_documents', [])
    contradictions = rule_results.get('contradictions', [])
    is_duplicate = rule_results.get('is_duplicate', claim.is_duplicate)

    reasons = []

    # ─────────────────────────────────────────────────────────────────────────
    # Deterministic Override Layer
    # ─────────────────────────────────────────────────────────────────────────
    final_decision = 'manual_review_required'

    # Check 1: Duplicate Claim
    if is_duplicate:
        final_decision = 'likely_invalid'
        reasons.append("Claim is flagged as a duplicate submission or shares identical document hashes.")

    # Check 2: Severe Temporal or Policy Contradictions
    elif len(contradictions) > 0:
        high_severity = [c for c in contradictions if c.get('severity') == 'high']
        if any(c.get('code') in ['C1_CLAIM_BEFORE_PURCHASE', 'C7_EXCLUDED_DAMAGE_TYPE'] for c in high_severity):
            final_decision = 'likely_invalid'
            reasons.append(f"Hard policy/temporal violations detected: {len(high_severity)} critical contradiction(s).")
        else:
            final_decision = 'manual_review_required'
            reasons.append(f"{len(contradictions)} data contradiction(s) require manual reviewer verification.")

    # Check 3: Missing Required Documentation
    elif len(missing_docs) > 0:
        final_decision = 'manual_review_required'
        reasons.append(f"Missing {len(missing_docs)} required documentation item(s): {', '.join(missing_docs)}.")

    # Check 4: Failed Core Warranty Rules
    elif failed_count > 0:
        # Check if critical rules failed (e.g., warranty expired or unauthorized repairs)
        failed_rule_names = [r['rule_name'] for r in rule_results.get('results', []) if not r.get('rule_passed')]
        if any(r in ['R1_WARRANTY_ACTIVE', 'R4_DAMAGE_TYPE_COVERED'] for r in failed_rule_names):
            final_decision = 'likely_invalid'
            reasons.append(f"Fundamental warranty criteria failed: {', '.join(failed_rule_names)}.")
        else:
            final_decision = 'manual_review_required'
            reasons.append(f"{failed_count} business rule(s) failed validation: {', '.join(failed_rule_names)}.")

    # Check 5: Model Disagreement or Uncertainty
    elif consistency in ['model_disagreement', 'uncertain_result']:
        final_decision = 'manual_review_required'
        reasons.append(f"AI models exhibited {consistency.replace('_', ' ')} (Python: {py_class} [{py_conf:.2f}], GTM: {gtm_class} [{gtm_conf:.2f}]).")

    # Check 6: Unanimous Valid Consensus
    elif py_class == 'valid' and gtm_class == 'valid' and failed_count == 0 and len(missing_docs) == 0:
        final_decision = 'likely_valid'
        reasons.append(f"Full consensus: All 14 business rules passed with high dual AI confidence ({py_conf:.2f}).")

    # Check 7: Unanimous Invalid Consensus
    elif py_class == 'invalid' and gtm_class == 'invalid':
        final_decision = 'likely_invalid'
        reasons.append(f"Both AI models classified claim as invalid with strong confidence ({py_conf:.2f}).")

    else:
        final_decision = 'manual_review_required'
        reasons.append("Claim requires human adjudicator sign-off based on multi-factor score distribution.")

    # ─────────────────────────────────────────────────────────────────────────
    # Update Claim Status in DB
    # ─────────────────────────────────────────────────────────────────────────
    status_map = {
        'likely_valid': 'approved',
        'likely_invalid': 'rejected',
        'manual_review_required': 'manual_review',
    }
    new_claim_status = status_map[final_decision]
    claim.status = new_claim_status
    claim.updated_at = datetime.utcnow()

    # ─────────────────────────────────────────────────────────────────────────
    # Persist ClaimDecision Record
    # ─────────────────────────────────────────────────────────────────────────
    explanation_json = {
        'reasons': reasons,
        'rules_evaluated': passed_count + failed_count,
        'rules_passed': passed_count,
        'rules_failed': failed_count,
        'missing_documents': missing_docs,
        'contradictions_count': len(contradictions),
        'is_duplicate': is_duplicate,
        'python_prediction': {
            'predicted_class': py_class,
            'top_confidence': py_conf,
        },
        'gtm_prediction': {
            'predicted_class': gtm_class,
            'top_confidence': gtm_conf,
        },
        'consistency_status': consistency,
        'confidence_difference': conf_diff,
    }

    decision_record = ClaimDecision.query.filter_by(claim_id=claim_id).first()
    if not decision_record:
        decision_record = ClaimDecision(
            claim_id=claim_id,
            python_predicted_class=py_class,
            python_top_confidence=py_conf,
            gtm_predicted_class=gtm_class,
            gtm_top_confidence=gtm_conf,
            confidence_difference=conf_diff,
            consistency_status=consistency,
            rules_passed_count=passed_count,
            rules_failed_count=failed_count,
            missing_doc_count=len(missing_docs),
            contradiction_count=len(contradictions),
            is_duplicate=is_duplicate,
            final_decision=final_decision,
            decision_explanation=explanation_json,
        )
        db.session.add(decision_record)
    else:
        decision_record.python_predicted_class = py_class
        decision_record.python_top_confidence = py_conf
        decision_record.gtm_predicted_class = gtm_class
        decision_record.gtm_top_confidence = gtm_conf
        decision_record.confidence_difference = conf_diff
        decision_record.consistency_status = consistency
        decision_record.rules_passed_count = passed_count
        decision_record.rules_failed_count = failed_count
        decision_record.missing_doc_count = len(missing_docs)
        decision_record.contradiction_count = len(contradictions)
        decision_record.is_duplicate = is_duplicate
        decision_record.final_decision = final_decision
        decision_record.decision_explanation = explanation_json
        decision_record.decided_at = datetime.utcnow()

    db.session.commit()

    # Log action to audit trail
    log_action(
        user_id=claim.user_id,
        action_type='claim_decision_synthesized',
        entity_type='claim_decision',
        entity_id=decision_record.decision_id,
        details={'final_decision': final_decision, 'new_status': new_claim_status},
    )

    # Notify claimant
    notify_claim_status_change(claim_id, new_claim_status, claim.user_id)

    return {
        'decision_id': decision_record.decision_id,
        'claim_id': claim_id,
        'final_decision': final_decision,
        'claim_status': new_claim_status,
        'consistency_status': consistency,
        'confidence_difference': conf_diff,
        'explanation': explanation_json,
    }
