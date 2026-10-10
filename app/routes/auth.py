"""
app/routes/auth.py
Authentication API endpoints (FR i).
Handles registration, login, logout, refresh, and current user identity.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt, create_access_token, create_refresh_token
from app.services.auth_service import register_user, login_user, logout_user
from app.models import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    ip = request.remote_addr
    success, res = register_user(data, ip_address=ip)
    if not success:
        status_code = res.get('status_code', 400)
        return jsonify(res), status_code
    claims = {'user_id': res['user_id'], 'role': res['role'], 'username': res['username']}
    return jsonify({
        'message': 'User registered successfully.',
        'user': res,
        'access_token': create_access_token(identity=res['user_id'], additional_claims=claims),
        'refresh_token': create_refresh_token(identity=res['user_id'], additional_claims=claims),
    }), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    identity_val = data.get('email') or data.get('username')
    password = data.get('password')
    ip = request.remote_addr

    if not identity_val or not password:
        return jsonify({'error': 'Email/Username and password are required.'}), 400

    success, res = login_user(identity_val, password, ip_address=ip)
    if not success:
        status_code = res.get('status_code', 401)
        return jsonify({'error': res.get('error', 'Authentication failed.')}), status_code

    return jsonify(res), 200


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    jti = get_jwt()['jti']
    user_id = get_jwt_identity()
    ip = request.remote_addr
    logout_user(jti, user_id=user_id, ip_address=ip)
    return jsonify({'message': 'Successfully logged out.'}), 200


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_me():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found.'}), 404
    return jsonify({'user': user.to_dict()}), 200


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh_token():
    from flask_jwt_extended import create_access_token
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not user.is_active:
        return jsonify({'error': 'User invalid or inactive.'}), 401

    claims = {'user_id': user.user_id, 'role': user.role, 'username': user.username}
    new_token = create_access_token(identity=user.user_id, additional_claims=claims)
    return jsonify({'access_token': new_token}), 200
