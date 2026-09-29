"""
app/routes/reviews.py
Human-in-the-loop review queue and reviewer action endpoints (FR xxxvi, xxxvii).
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.extensions import db
from app.models import Claim, ReviewerAction, ClaimDecision
from app.utils.validators import validate_reviewer_action_payload
from app.services.auth_service import role_required
from app.services.audit_service import log_action
from app.services.notification_service import notify_claim_status_change

reviews_bp = Blueprint('reviews', __name__)


@reviews_bp.route('/queue', methods=['GET'])
@role_required('reviewer', 'service_employee', 'admin')
def get_review_queue():
    """Retrieve all claims in manual_review, additional_info_required, or under_evaluation state."""
    status_filter = request.args.get('status')
    if status_filter:
        claims = Claim.query.filter_by(status=status_filter).order_by(Claim.updated_at.desc()).all()
    else:
        claims = Claim.query.filter(
            Claim.status.in_(['manual_review', 'additional_info_required', 'under_evaluation'])
        ).order_by(Claim.updated_at.desc()).all()

    queue_data = []
    for c in claims:
        d = ClaimDecision.query.filter_by(claim_id=c.claim_id).first()
        queue_data.append({
            'claim_id': c.claim_id,
            'user_id': c.user_id,
            'product_id': c.product_id,
            'product_name': c.product.product_name if c.product else '',
            'category': c.product.category if c.product else '',
            'fault_description': c.fault_description,
            'status': c.status,
            'damage_type': c.damage_type,
            'missing_doc_count': c.missing_doc_count,
            'contradiction_count': c.contradiction_count,
            'is_duplicate': c.is_duplicate,
            'final_decision': d.final_decision if d else None,
            'consistency_status': d.consistency_status if d else None,
            'created_at': c.created_at.isoformat(),
        })

    return jsonify({
        'queue_count': len(queue_data),
        'queue': queue_data,
        'claims': queue_data
    }), 200


@reviews_bp.route('/adjudicate', methods=['POST'])
@role_required('reviewer', 'service_employee', 'admin')
def adjudicate_claim_alias():
    data = request.get_json() or {}
    claim_id = data.get('claim_id')
    if not claim_id:
        return jsonify({'error': 'claim_id is required.'}), 400
    return take_review_action(claim_id)


@reviews_bp.route('/<claim_id>/action', methods=['POST'])
@role_required('reviewer', 'service_employee', 'admin')
def take_review_action(claim_id):
    reviewer_id = get_jwt_identity()
    data = request.get_json() or {}

    valid, errors = validate_reviewer_action_payload(data)
    if not valid:
        return jsonify({'errors': errors}), 400

    claim = Claim.query.get(claim_id)
    if not claim:
        return jsonify({'error': 'Claim not found.'}), 404

    action_type = str(data.get('action_type') or data.get('action') or '').strip().lower()
    if action_type in ['request_info', 'request-info']:
        action_type = 'request_info'
    override_decision = data.get('override_decision')
    comments = data.get('comments') or data.get('notes', '')


    # Apply state transitions
    if action_type == 'approve':
        claim.status = 'approved'
    elif action_type == 'reject':
        claim.status = 'rejected'
    elif action_type == 'request_info':
        claim.status = 'additional_info_required'
    elif action_type == 'override':
        if override_decision in ['approved', 'rejected']:
            claim.status = override_decision
        else:
            return jsonify({'error': "Override decision must be 'approved' or 'rejected'."}), 400

    claim.updated_at = datetime.utcnow()

    # Record action
    action_rec = ReviewerAction(
        claim_id=claim_id,
        reviewer_id=reviewer_id,
        action_type=action_type,
        override_decision=override_decision,
        comments=comments,
    )
    db.session.add(action_rec)
    db.session.commit()

    log_action(
        user_id=reviewer_id,
        action_type=f'reviewer_action_{action_type}',
        entity_type='claim',
        entity_id=claim_id,
        details={'comments': comments, 'new_status': claim.status, 'override': override_decision},
        ip_address=request.remote_addr,
    )

    # Notify claimant
    notify_claim_status_change(claim_id, claim.status, claim.user_id)

    return jsonify({
        'message': f"Claim {action_type} action applied successfully.",
        'claim_id': claim_id,
        'new_status': claim.status,
        'action': action_rec.to_dict(),
    }), 200
