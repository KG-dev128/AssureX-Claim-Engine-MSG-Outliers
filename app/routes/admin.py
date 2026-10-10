"""
app/routes/admin.py
System administration, role management, audit inspection, anomaly resolution, and policy editing (FR i, xxvi, xlvii, l).
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models import User, AuditTrail, AnomalyAlert, WarrantyPolicy
from app.services.auth_service import role_required
from app.services.audit_service import log_action
from app.services.policy_service import list_all_policies, update_policy

admin_bp = Blueprint('admin', __name__)


# ── User Administration ───────────────────────────────────────────────────────

@admin_bp.route('/users', methods=['GET'])
@role_required('admin')
def get_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({
        'count': len(users),
        'users': [u.to_dict() for u in users]
    }), 200


@admin_bp.route('/users/<user_id>/role', methods=['PUT'])
@role_required('admin')
def update_user_role(user_id):
    admin_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found.'}), 404

    data = request.get_json() or {}
    new_role = data.get('role')
    is_active = data.get('is_active')

    if new_role:
        if new_role not in ['customer', 'service_employee', 'reviewer', 'admin']:
            return jsonify({'error': 'Invalid role.'}), 400
        user.role = new_role

    if is_active is not None:
        user.is_active = bool(is_active)

    db.session.commit()

    log_action(
        user_id=admin_id,
        action_type='admin_updated_user',
        entity_type='user',
        entity_id=user_id,
        details={'new_role': new_role, 'is_active': is_active},
        ip_address=request.remote_addr,
    )

    return jsonify({'message': 'User updated.', 'user': user.to_dict()}), 200


# ── Audit Trail (FR xlvii) ───────────────────────────────────────────────────

@admin_bp.route('/audit', methods=['GET'])
@role_required('admin')
def get_audit_trail():
    query = AuditTrail.query
    user_id = request.args.get('user_id')
    action = request.args.get('action_type')

    if user_id:
        query = query.filter_by(user_id=user_id)
    if action:
        query = query.filter_by(action_type=action)

    logs = query.order_by(AuditTrail.occurred_at.desc()).limit(100).all()
    return jsonify({'count': len(logs), 'audit_trail': [l.to_dict() for l in logs]}), 200


# ── Anomaly Alerts (FR l) ─────────────────────────────────────────────────────

@admin_bp.route('/anomalies', methods=['GET'])
@role_required('admin', 'reviewer')
def get_anomalies():
    unresolved_only = request.args.get('unresolved', 'true') == 'true'
    query = AnomalyAlert.query
    if unresolved_only:
        query = query.filter_by(is_resolved=False)

    alerts = query.order_by(AnomalyAlert.created_at.desc()).all()
    return jsonify({'count': len(alerts), 'alerts': [a.to_dict() for a in alerts]}), 200


@admin_bp.route('/anomalies/<alert_id>/resolve', methods=['PUT'])
@role_required('admin', 'reviewer')
def resolve_anomaly(alert_id):
    alert = AnomalyAlert.query.get(alert_id)
    if not alert:
        return jsonify({'error': 'Alert not found.'}), 404

    alert.is_resolved = True
    db.session.commit()

    log_action(
        user_id=get_jwt_identity(),
        action_type='anomaly_resolved',
        entity_type='anomaly_alert',
        entity_id=alert_id,
        ip_address=request.remote_addr,
    )

    return jsonify({'message': 'Alert resolved.', 'alert': alert.to_dict()}), 200


# ── Warranty Policy Management (FR xxvi) ──────────────────────────────────────

@admin_bp.route('/policies', methods=['GET'])
@role_required('admin', 'reviewer')
def get_policies():
    policies = list_all_policies()
    return jsonify({'policies': policies}), 200


@admin_bp.route('/policies/<category>', methods=['PUT'])
@role_required('admin')
def modify_policy(category):
    admin_id = get_jwt_identity()
    data = request.get_json() or {}
    if not data:
        return jsonify({'error': 'Policy configuration payload required.'}), 400

    policy = update_policy(category, data, admin_user_id=admin_id)

    log_action(
        user_id=admin_id,
        action_type='warranty_policy_updated',
        entity_type='warranty_policy',
        entity_id=policy.policy_id,
        details={'category': category, 'version': policy.version},
        ip_address=request.remote_addr,
    )

    return jsonify({'message': f'Policy for {category} updated.', 'policy': policy.to_dict()}), 200


@admin_bp.route('/config/reload', methods=['POST'])
@admin_bp.route('/policies/reload', methods=['POST'])
@role_required('admin')
def reload_configuration():
    admin_id = get_jwt_identity()
    from app.services.policy_service import seed_default_policies, list_all_policies
    seed_default_policies()
    policies = list_all_policies()

    log_action(
        user_id=admin_id,
        action_type='config_reloaded',
        entity_type='system_configuration',
        entity_id='policies_thresholds',
        details={'policy_count': len(policies), 'action': 'manual_admin_reload'},
        ip_address=request.remote_addr,
    )

    return jsonify({
        'message': 'Configuration and warranty policies reloaded successfully.',
        'policies': policies,
        'status': 'reloaded'
    }), 200


@admin_bp.route('/products/<product_id>/generate-artifacts', methods=['POST'])
@role_required('admin')
def admin_generate_artifacts(product_id):
    from app.services.document_artifact_generator import generate_policy_artifacts_for_product
    options = request.get_json() or {}
    try:
        result = generate_policy_artifacts_for_product(product_id, admin_user_id=get_jwt_identity(), options=options)
        return jsonify({
            'message': f"Generated {result['count']} policy artifacts for {result['product_name']}.",
            'result': result
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/seed-test-data', methods=['POST'])
@role_required('admin')
def admin_seed_test_data():
    """Trigger full testing dataset seeding: categorized products, artifacts, valid/invalid/manual-review claims, and CSV splits."""
    from app.services.test_dataset_seeder import run_full_dataset_seeding
    try:
        stats = run_full_dataset_seeding()
        return jsonify({
            'message': 'Testing dataset generated and seeded successfully!',
            'stats': stats
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


