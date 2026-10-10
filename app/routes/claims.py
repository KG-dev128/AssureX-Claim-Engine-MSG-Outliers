"""
app/routes/claims.py
Core claim lifecycle, submission, and automated evaluation routes (FR x, xi, xx, xxv, xxviii, xxx, xxxiv, xxxv).
"""
import os
from datetime import datetime, date
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.extensions import db
from app.models import Claim, Product, Warranty, Document, ClaimDecision, RuleValidationResult
from app.utils.validators import validate_claim_payload
from app.utils.date_utils import parse_date_flexible
from app.services.audit_service import log_action
from app.services.card_generator import generate_claim_summary_card
from app.services.rule_engine import evaluate_warranty_rules
from app.services.contradiction_detector import detect_contradictions
from app.services.duplicate_detector import detect_duplicate_claim
from app.services.ml_service import predict_claim
from app.services.gtm_service import predict_gtm
from app.services.decision_engine import evaluate_final_decision

claims_bp = Blueprint('claims', __name__)


@claims_bp.route('/', methods=['POST'])
@jwt_required()
def create_claim():
    user_id = get_jwt_identity()
    claims_claims = get_jwt()
    role = claims_claims.get('role', 'customer')
    data = request.get_json() or {}

    valid, errors = validate_claim_payload(data)
    if not valid:
        return jsonify({'errors': errors}), 400

    product = Product.query.get(data['product_id'])
    if not product:
        return jsonify({'error': 'Product not found.'}), 404

    # Security: Customer can only submit claims for products they own
    if role == 'customer' and product.user_id != user_id:
        return jsonify({'error': 'Forbidden: You can only file claims for products registered to your account.'}), 403

    # Select latest or active warranty
    warranty = Warranty.query.filter_by(product_id=product.product_id).order_by(Warranty.expiry_date.desc()).first()
    if not warranty:
        return jsonify({'error': 'No warranty found for this product.'}), 400

    raw_date = data.get('fault_occurrence_date') or data.get('fault_date')
    fault_date = parse_date_flexible(str(raw_date))
    product_age_days = (fault_date - product.purchase_date).days

    claim = Claim(
        user_id=user_id,
        product_id=product.product_id,
        warranty_id=warranty.warranty_id,
        product_age_days=max(0, product_age_days),
        fault_occurrence_date=fault_date,
        fault_description=data['fault_description'].strip(),
        damage_type=data.get('damage_type', 'other'),
        previous_replacement=bool(data.get('previous_replacement', False)),
        status='draft',
    )
    db.session.add(claim)
    db.session.commit()

    log_action(
        user_id=user_id,
        action_type='claim_created_draft',
        entity_type='claim',
        entity_id=claim.claim_id,
        details={'product_id': product.product_id},
        ip_address=request.remote_addr,
    )

    # If auto_evaluate explicitly requested
    if data.get('auto_evaluate', False):
        claim.status = 'submitted'
        claim.claim_submission_date = date.today()
        claim.updated_at = datetime.utcnow()
        db.session.commit()
        resp = evaluate_claim(claim.claim_id)
        if isinstance(resp, tuple):
            return resp[0], 201
        return resp, 201

    return jsonify({
        'message': 'Draft claim created successfully.',
        'claim_id': claim.claim_id,
        'claim': claim.to_dict()
    }), 201



@claims_bp.route('/', methods=['GET'])
@jwt_required()
def list_claims():
    user_id = get_jwt_identity()
    claims_claims = get_jwt()
    role = claims_claims.get('role', 'customer')

    status_filter = request.args.get('status')
    query = Claim.query

    if role == 'customer':
        query = query.filter_by(user_id=user_id)
    else:
        # Service employee, reviewer, admin can filter by user or status
        if request.args.get('user_id'):
            query = query.filter_by(user_id=request.args.get('user_id'))

    if status_filter:
        query = query.filter_by(status=status_filter)

    results = query.order_by(Claim.created_at.desc()).all()
    return jsonify({
        'count': len(results),
        'claims': [c.to_dict() for c in results]
    }), 200


@claims_bp.route('/<claim_id>', methods=['GET'])
@jwt_required()
def get_claim(claim_id):
    user_id = get_jwt_identity()
    claims_claims = get_jwt()
    role = claims_claims.get('role', 'customer')

    claim = Claim.query.get(claim_id)
    if not claim:
        return jsonify({'error': 'Claim not found.'}), 404

    if role == 'customer' and claim.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    product = Product.query.get(claim.product_id)
    warranty = Warranty.query.get(claim.warranty_id)
    docs = [d.to_dict() for d in Document.query.filter_by(claim_id=claim_id).all()]
    decision = ClaimDecision.query.filter_by(claim_id=claim_id).first()

    data = claim.to_dict()
    data['product'] = product.to_dict() if product else None
    data['warranty'] = warranty.to_dict() if warranty else None
    data['documents'] = docs
    data['decision'] = decision.to_dict() if decision else None

    return jsonify({'claim': data}), 200


@claims_bp.route('/<claim_id>/submit', methods=['POST'])
@jwt_required()
def submit_claim(claim_id):
    user_id = get_jwt_identity()
    claim = Claim.query.get(claim_id)
    if not claim:
        return jsonify({'error': 'Claim not found.'}), 404

    if claim.user_id != user_id and get_jwt().get('role') not in ['admin', 'reviewer']:
        return jsonify({'error': 'Forbidden.'}), 403

    claim.status = 'submitted'
    claim.claim_submission_date = date.today()
    claim.updated_at = datetime.utcnow()
    db.session.commit()

    log_action(
        user_id=user_id,
        action_type='claim_submitted',
        entity_type='claim',
        entity_id=claim_id,
        ip_address=request.remote_addr,
    )

    # Immediately trigger evaluation pipeline
    return evaluate_claim(claim_id)


@claims_bp.route('/<claim_id>/card', methods=['GET'])
@jwt_required()
def get_claim_card(claim_id):
    claim = Claim.query.get(claim_id)
    if not claim:
        return jsonify({'error': 'Claim not found.'}), 404

    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and claim.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    variation = request.args.get('variation', 'default')
    card_path = generate_claim_summary_card(claim_id, variation=variation)

    if request.args.get('download') == 'true' and os.path.exists(card_path):
        return send_file(os.path.abspath(card_path), mimetype='image/png')

    return jsonify({
        'claim_id': claim_id,
        'card_path': card_path,
        'variation': variation,
    }), 200


@claims_bp.route('/<claim_id>/rules', methods=['GET'])
@jwt_required()
def get_claim_rules(claim_id):
    claim = Claim.query.get(claim_id)
    if not claim:
        return jsonify({'error': 'Claim not found.'}), 404

    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and claim.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    results = evaluate_warranty_rules(claim_id)
    return jsonify({'claim_id': claim_id, 'validation': results}), 200


@claims_bp.route('/<claim_id>/contradictions', methods=['GET'])
@jwt_required()
def get_claim_contradictions(claim_id):
    claim = Claim.query.get(claim_id)
    if not claim:
        return jsonify({'error': 'Claim not found.'}), 404

    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and claim.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    results = detect_contradictions(claim_id)
    return jsonify({'claim_id': claim_id, 'contradictions_count': len(results), 'contradictions': results}), 200


@claims_bp.route('/<claim_id>/duplicates', methods=['GET'])
@jwt_required()
def get_claim_duplicates(claim_id):
    claim = Claim.query.get(claim_id)
    if not claim:
        return jsonify({'error': 'Claim not found.'}), 404

    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and claim.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    results = detect_duplicate_claim(claim_id)
    return jsonify({'claim_id': claim_id, 'duplicate_check': results}), 200


@claims_bp.route('/<claim_id>/evaluate', methods=['POST'])
@jwt_required()
def evaluate_claim(claim_id):
    """
    Executes full automated evaluation pipeline:
    1. Card generation
    2. 14 deterministic business rules
    3. Python tabular ML model inference
    4. GTM visual ML model inference
    5. Final decision synthesis
    """
    claim = Claim.query.get(claim_id)
    if not claim:
        return jsonify({'error': 'Claim not found.'}), 404

    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and claim.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    claim.status = 'under_evaluation'
    db.session.commit()

    # Step 1: Summary Card
    card_path = generate_claim_summary_card(claim_id)

    # Step 2: 14 Rules
    rule_results = evaluate_warranty_rules(claim_id)

    # Step 3: Python Tabular ML
    py_pred = predict_claim(claim_id)

    # Step 4: GTM Visual ML
    gtm_pred = predict_gtm(claim_id, card_path)

    # Step 5: Synthesize Decision
    final_res = evaluate_final_decision(claim_id, py_pred, gtm_pred, rule_results)

    return jsonify({
        'message': 'Claim evaluation completed.',
        'claim_id': claim_id,
        'claim': claim.to_dict(),
        'status': final_res['claim_status'],
        'decision': final_res['final_decision'],
        'consistency': final_res['consistency_status'],
        'python_prediction': py_pred,
        'gtm_prediction': gtm_pred,
        'rules': rule_results,
        'explanation': final_res['explanation'],
    }), 200


@claims_bp.route('/<claim_id>/decision', methods=['GET'])
@jwt_required()
def get_claim_decision(claim_id):
    claim = Claim.query.get(claim_id)
    if not claim:
        return jsonify({'error': 'Claim not found.'}), 404

    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and claim.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    dec = ClaimDecision.query.filter_by(claim_id=claim_id).first()
    if not dec:
        return jsonify({'error': 'Decision not yet generated for this claim.'}), 404
    return jsonify({'decision': dec.to_dict()}), 200

