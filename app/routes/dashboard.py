"""
app/routes/dashboard.py
Dashboard analytics, operational KPIs, and activity summaries (FR xl, xli).
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models import Claim, Product, Warranty, ClaimDecision, AnomalyAlert, Notification, AuditTrail

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_stats():
    user_id = get_jwt_identity()
    claims_jwt = get_jwt()
    role = claims_jwt.get('role', 'customer')

    if role == 'customer':
        total_claims = Claim.query.filter_by(user_id=user_id).count()
        approved = Claim.query.filter_by(user_id=user_id, status='approved').count()
        rejected = Claim.query.filter_by(user_id=user_id, status='rejected').count()
        pending = Claim.query.filter(
            Claim.user_id == user_id,
            Claim.status.in_(['draft', 'submitted', 'under_evaluation', 'manual_review', 'additional_info_required'])
        ).count()
        products = Product.query.filter_by(user_id=user_id).count()

        return jsonify({
            'role': 'customer',
            'stats': {
                'total_claims': total_claims,
                'approved_claims': approved,
                'rejected_claims': rejected,
                'pending_claims': pending,
                'registered_products': products,
            },
            'total_claims': total_claims,
            'approved_claims': approved,
            'rejected_claims': rejected,
            'pending_claims': pending,
            'registered_products': products,
        }), 200

    if role == 'service_employee':
        from app.models import RepairHistory
        from datetime import date
        total_repairs = RepairHistory.query.count()
        total_products = Product.query.count()
        active_warranties = Warranty.query.filter(Warranty.expiry_date >= date.today()).count()
        pending_service_claims = Claim.query.filter(
            Claim.status.in_(['under_evaluation', 'manual_review', 'submitted'])
        ).count()
        return jsonify({
            'role': 'service_employee',
            'stats': {
                'total_repairs': total_repairs,
                'total_products': total_products,
                'active_warranties': active_warranties,
                'pending_service_claims': pending_service_claims,
            },
            'total_repairs': total_repairs,
            'total_products': total_products,
            'active_warranties': active_warranties,
            'pending_service_claims': pending_service_claims,
        }), 200

    # Reviewer / Admin view
    total_claims = Claim.query.count()
    approved = Claim.query.filter_by(status='approved').count()
    rejected = Claim.query.filter_by(status='rejected').count()
    manual_review = Claim.query.filter_by(status='manual_review').count()
    under_eval = Claim.query.filter_by(status='under_evaluation').count()
    submitted = Claim.query.filter_by(status='submitted').count()

    total_products = Product.query.count()
    total_warranties = Warranty.query.count()
    unresolved_anomalies = AnomalyAlert.query.filter_by(is_resolved=False).count()

    # Consistency breakdown
    decisions = ClaimDecision.query.all()
    consistency_counts = {}
    for d in decisions:
        st = d.consistency_status or 'uncertain_result'
        consistency_counts[st] = consistency_counts.get(st, 0) + 1

    approval_rate = round(approved / max(1, (approved + rejected)) * 100, 1)
    stats_obj = {
        'total_claims': total_claims,
        'approved_claims': approved,
        'rejected_claims': rejected,
        'manual_review_queue': manual_review,
        'under_evaluation': under_eval,
        'active_anomalies': unresolved_anomalies,
        'total_products': total_products,
        'total_warranties': total_warranties,
        'approval_rate': approval_rate,
    }

    return jsonify({
        'role': role,
        'stats': stats_obj,
        'total_claims': total_claims,
        'approval_rate': approval_rate,
        'manual_review_queue': manual_review,
        'active_anomalies': unresolved_anomalies,
        'claims_summary': {
            'total': total_claims,
            'approved': approved,
            'rejected': rejected,
            'manual_review': manual_review,
            'under_evaluation': under_eval,
            'submitted': submitted,
            'approval_rate': approval_rate,
        },
        'system_assets': {
            'products': total_products,
            'warranties': total_warranties,
            'anomalies_pending': unresolved_anomalies,
        },
        'model_consistency_breakdown': consistency_counts,
    }), 200


@dashboard_bp.route('/recent', methods=['GET'])
@jwt_required()
def get_recent_activity():
    user_id = get_jwt_identity()
    claims_jwt = get_jwt()
    role = claims_jwt.get('role', 'customer')

    if role == 'customer':
        recent_claims = Claim.query.filter_by(user_id=user_id).order_by(Claim.created_at.desc()).limit(5).all()
        notifs = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.created_at.desc()).limit(10).all()
        recent_audits = []
    elif role == 'service_employee':
        recent_claims = Claim.query.order_by(Claim.updated_at.desc()).limit(8).all()
        notifs = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.created_at.desc()).limit(10).all()
        recent_audits = []
    else:
        recent_claims = Claim.query.order_by(Claim.updated_at.desc()).limit(10).all()
        notifs = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(10).all()
        recent_audits = AuditTrail.query.order_by(AuditTrail.occurred_at.desc()).limit(10).all()

    return jsonify({
        'recent_claims': [c.to_dict() for c in recent_claims],
        'unread_notifications': [n.to_dict() for n in notifs],
        'recent_audit_trail': [a.to_dict() for a in recent_audits],
    }), 200


@dashboard_bp.route('/notifications', methods=['GET'])
@jwt_required()
def get_user_notifications_route():
    user_id = get_jwt_identity()
    from app.services.notification_service import get_user_notifications
    notifs = get_user_notifications(user_id, unread_only=False, limit=50)
    return jsonify({'count': len(notifs), 'notifications': notifs}), 200


@dashboard_bp.route('/notifications/read-all', methods=['POST'])
@jwt_required()
def read_all_notifications_route():
    user_id = get_jwt_identity()
    from app.services.notification_service import mark_all_notifications_read
    count = mark_all_notifications_read(user_id)
    return jsonify({'message': f'{count} notifications marked as read.', 'marked_count': count}), 200


