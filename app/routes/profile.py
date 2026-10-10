"""
app/routes/profile.py
User profile management endpoints (FR ii).
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models import UserProfile, User
from app.services.audit_service import log_action

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/', methods=['GET'])
@jwt_required()
def get_profile():
    user_id = get_jwt_identity()
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found.'}), 404
        profile = UserProfile(user_id=user_id, full_name=user.username)
        db.session.add(profile)
        db.session.commit()
    return jsonify({'profile': profile.to_dict()}), 200


@profile_bp.route('/', methods=['PUT'])
@jwt_required()
def update_profile():
    user_id = get_jwt_identity()
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id, full_name="User")
        db.session.add(profile)

    data = request.get_json() or {}
    if 'full_name' in data:
        profile.full_name = data['full_name']
    if 'phone' in data:
        profile.phone = data['phone']
    if 'address' in data:
        profile.address = data['address']
    if 'organization' in data:
        profile.organization = data['organization']

    db.session.commit()

    log_action(
        user_id=user_id,
        action_type='profile_updated',
        entity_type='user_profile',
        entity_id=profile.profile_id,
        details=data,
        ip_address=request.remote_addr,
    )

    return jsonify({'message': 'Profile updated successfully.', 'profile': profile.to_dict()}), 200


@profile_bp.route('/password', methods=['PUT'])
@jwt_required()
def update_password():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found.'}), 404

    data = request.get_json() or {}
    old_password = data.get('old_password')
    new_password = data.get('new_password')

    if not old_password or not new_password:
        return jsonify({'error': 'Both old and new passwords are required.'}), 400

    from app.extensions import bcrypt
    if not bcrypt.check_password_hash(user.password_hash, old_password):
        return jsonify({'error': 'Current password is incorrect.'}), 400

    if len(new_password) < 8:
        return jsonify({'error': 'New password must be at least 8 characters long.'}), 400

    user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
    db.session.commit()

    log_action(
        user_id=user_id,
        action_type='password_changed',
        entity_type='user',
        entity_id=user_id,
        ip_address=request.remote_addr,
    )

    return jsonify({'message': 'Password updated successfully.'}), 200

