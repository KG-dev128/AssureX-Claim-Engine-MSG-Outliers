"""
app/services/auth_service.py
Authentication, password hashing, JWT generation, RBAC decorators, and session security (FR i, ii, l).
"""
from datetime import datetime
from functools import wraps
from typing import Dict, Any, Tuple, Optional
import os
from flask import abort, current_app, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity, jwt_required, get_jwt
from app.extensions import db, bcrypt, jwt_blocklist
from app.models import User, UserProfile, AnomalyAlert
from app.utils.validators import validate_registration
from .audit_service import log_action


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    return bcrypt.generate_password_hash(password).decode('utf-8')


def check_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash."""
    return bcrypt.check_password_hash(hashed, password)


def register_user(data: Dict[str, Any], ip_address: Optional[str] = None) -> Tuple[bool, Any]:
    """Register a new user with UserProfile and audit record."""
    valid, errors = validate_registration(data)
    if not valid:
        return False, {'errors': errors, 'status_code': 400}

    # Check unique username and email
    if User.query.filter_by(username=data['username']).first():
        return False, {'errors': {'username': 'Username already exists.'}, 'status_code': 409}
    if User.query.filter_by(email=data['email']).first():
        return False, {'errors': {'email': 'Email already registered.'}, 'status_code': 409}

    pw_hash = hash_password(data['password'])
    # Default to customer; allow explicit valid role if provided
    role = data.get('role', 'customer')
    if role not in ['customer', 'service_employee', 'reviewer', 'admin']:
        role = 'customer'

    user = User(
        username=data['username'],
        email=data['email'],
        password_hash=pw_hash,
        role=role,
    )
    db.session.add(user)
    db.session.flush()

    # Create associated profile
    profile = UserProfile(
        user_id=user.user_id,
        full_name=data.get('full_name', data['username']),
        phone=data.get('phone'),
        address=data.get('address'),
        organization=data.get('organization'),
    )
    db.session.add(profile)
    db.session.commit()

    # Log to audit trail
    log_action(
        user_id=user.user_id,
        action_type='user_registered',
        entity_type='user',
        entity_id=user.user_id,
        details={'username': user.username, 'role': user.role},
        ip_address=ip_address,
    )

    return True, user.to_dict()


def login_user(identity_input: str, password: str, ip_address: Optional[str] = None) -> Tuple[bool, Any]:
    """
    Authenticate user by email or username.
    Enforces lockout detection and audit logging.
    """
    user = User.query.filter(
        (User.email == identity_input) | (User.username == identity_input)
    ).first()

    if not user:
        return False, {'error': 'Invalid credentials.', 'status_code': 401}

    if not user.is_active:
        return False, {'error': 'Account is suspended or deactivated.', 'status_code': 403}

    if not check_password(password, user.password_hash):
        user.failed_login_count += 1
        db.session.commit()

        log_action(
            user_id=user.user_id,
            action_type='login_failed',
            entity_type='user',
            entity_id=user.user_id,
            details={'attempts': user.failed_login_count},
            ip_address=ip_address,
        )

        # Trigger anomaly alert if repeated failures
        if user.failed_login_count >= 5:
            alert = AnomalyAlert(
                alert_type='multiple_failed_logins',
                severity='high',
                message=f"User {user.username} exceeded 5 consecutive failed logins.",
                related_user_id=user.user_id,
            )
            db.session.add(alert)
            db.session.commit()

        return False, {'error': 'Invalid credentials.', 'status_code': 401}

    # Reset failed attempts and update last login
    user.failed_login_count = 0
    user.last_login = datetime.utcnow()
    db.session.commit()

    # Claims payload for token
    token_claims = {
        'user_id': user.user_id,
        'role': user.role,
        'username': user.username,
    }

    access_token = create_access_token(
        identity=user.user_id,
        additional_claims=token_claims
    )
    refresh_token = create_refresh_token(
        identity=user.user_id,
        additional_claims=token_claims
    )

    log_action(
        user_id=user.user_id,
        action_type='login_successful',
        entity_type='user',
        entity_id=user.user_id,
        ip_address=ip_address,
    )

    return True, {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': user.to_dict(),
    }


def logout_user(jti: str, user_id: Optional[str] = None, ip_address: Optional[str] = None) -> bool:
    """Invalidate JWT access or refresh token."""
    jwt_blocklist.add(jti)
    if user_id:
        log_action(
            user_id=user_id,
            action_type='user_logged_out',
            entity_type='user',
            entity_id=user_id,
            ip_address=ip_address,
        )
    return True


def role_required(*allowed_roles):
    """
    Decorator for endpoints requiring specific role(s).
    Allowed roles: customer, service_employee, reviewer, admin.
    """
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            user_role = claims.get('role')
            if not user_role or user_role not in allowed_roles:
                return jsonify({
                    'error': 'Forbidden: Insufficient privileges for this operation.',
                    'required_roles': list(allowed_roles),
                    'your_role': user_role
                }), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def ensure_initial_admin_seeded():
    """Seed the root Administrator only when an operator supplies its password."""
    admin_email = 'admin@assurex.com'
    admin_username = 'admin'
    existing = User.query.filter(
        (User.email == admin_email) | (User.username == admin_username)
    ).first()

    if not existing:
        initial_password = os.getenv('INITIAL_ADMIN_PASSWORD')
        if not initial_password:
            current_app.logger.warning(
                'Initial admin was not created. Set INITIAL_ADMIN_PASSWORD to provision it securely.'
            )
            return
        pw_hash = hash_password(initial_password)
        user = User(
            username=admin_username,
            email=admin_email,
            password_hash=pw_hash,
            role='admin',
            is_active=True,
        )
        db.session.add(user)
        db.session.flush()

        profile = UserProfile(
            user_id=user.user_id,
            full_name='System Administrator',
            phone='+1 (555) 000-0001',
            organization='AssureX Global Enterprise'
        )
        db.session.add(profile)
        db.session.commit()
    else:
        # Guarantee admin role and active status
        if existing.role != 'admin' or not existing.is_active:
            existing.role = 'admin'
            existing.is_active = True
            db.session.commit()

