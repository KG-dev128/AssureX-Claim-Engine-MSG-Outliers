"""
app/utils/validators.py
Input validation helpers and payload checkers (FR xv).
Ensures data hygiene, prevents malformed requests, and returns descriptive errors.
"""
import re
from datetime import datetime, date
from typing import Dict, Any, List, Tuple

VALID_ROLES = {'customer', 'service_employee', 'reviewer', 'admin'}
VALID_CATEGORIES = {'electronics', 'appliances', 'automotive', 'general'}
VALID_WARRANTY_TYPES = {'standard', 'extended'}
VALID_DAMAGE_TYPES = {
    'electrical_failure',
    'mechanical_failure',
    'screen_crack',
    'water_damage',
    'wear_and_tear',
    'battery_degradation',
    'software_glitch',
    'other',
}
DAMAGE_TYPE_ALIASES = {
    'hardware_failure': 'mechanical_failure',
    'screen_damage': 'screen_crack',
    'battery_failure': 'battery_degradation',
    'audio_defect': 'electrical_failure',
    'motherboard': 'electrical_failure',
    'water_liquid': 'water_damage',
}
VALID_REVIEW_ACTIONS = {'approve', 'reject', 'request_info', 'override'}


def validate_email(email: str) -> bool:
    """Validate RFC 5322 standard email address format."""
    if not email or not isinstance(email, str):
        return False
    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return bool(re.match(pattern, email.strip()))


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """Check password meets baseline security standards."""
    if not password or len(password) < 6:
        return False, "Password must be at least 6 characters long."
    return True, ""


def validate_registration(data: Dict[str, Any]) -> Tuple[bool, Dict[str, str]]:
    errors = {}
    if not data:
        return False, {"body": "Request body cannot be empty."}

    username = str(data.get('username', '')).strip()
    if not username or len(username) < 3:
        errors['username'] = "Username is required and must be at least 3 characters."

    email = str(data.get('email', '')).strip()
    if not validate_email(email):
        errors['email'] = "A valid email address is required."

    password = str(data.get('password', ''))
    valid_pass, msg = validate_password_strength(password)
    if not valid_pass:
        errors['password'] = msg

    role = data.get('role', 'customer')
    if role not in VALID_ROLES:
        errors['role'] = f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}"

    return len(errors) == 0, errors


def validate_product_payload(data: Dict[str, Any]) -> Tuple[bool, Dict[str, str]]:
    errors = {}
    if not data:
        return False, {"body": "Request payload is required."}

    required_fields = ['product_name', 'category', 'brand', 'model_number', 'serial_number', 'purchase_date']
    for f in required_fields:
        if not data.get(f):
            errors[f] = f"Field '{f}' is required."

    cat = str(data.get('category', '')).strip().lower()
    if cat and cat not in VALID_CATEGORIES:
        errors['category'] = f"Category must be one of: {', '.join(sorted(VALID_CATEGORIES))}"

    if data.get('purchase_date'):
        try:
            from .date_utils import parse_date_flexible
            parse_date_flexible(str(data['purchase_date']))
        except Exception:
            errors['purchase_date'] = "Purchase date format invalid. Use YYYY-MM-DD."

    return len(errors) == 0, errors


def validate_claim_payload(data: Dict[str, Any]) -> Tuple[bool, Dict[str, str]]:
    errors = {}
    if not data:
        return False, {"body": "Request payload is required."}

    if not data.get('product_id'):
        errors['product_id'] = "Product ID is required."

    if not data.get('fault_description') or len(str(data['fault_description']).strip()) < 5:
        errors['fault_description'] = "Fault description must be at least 5 characters long."

    raw_date = data.get('fault_occurrence_date') or data.get('fault_date')
    if not raw_date:
        errors['fault_occurrence_date'] = "Fault occurrence date is required."
    else:
        try:
            from .date_utils import parse_date_flexible
            fault_dt = parse_date_flexible(str(raw_date))
            if fault_dt > date.today():
                errors['fault_occurrence_date'] = "Fault occurrence date cannot be in the future."
        except Exception:
            errors['fault_occurrence_date'] = "Fault occurrence date format invalid. Use YYYY-MM-DD."

    if data.get('damage_type'):
        damage_type = str(data['damage_type']).strip().lower()
        damage_type = DAMAGE_TYPE_ALIASES.get(damage_type, damage_type)
        if damage_type not in VALID_DAMAGE_TYPES:
            errors['damage_type'] = f"Damage type must be one of: {', '.join(sorted(VALID_DAMAGE_TYPES))}"
        else:
            data['damage_type'] = damage_type

    return len(errors) == 0, errors


def validate_reviewer_action_payload(data: Dict[str, Any]) -> Tuple[bool, Dict[str, str]]:
    errors = {}
    if not data:
        return False, {"body": "Request payload is required."}

    action_type = str(data.get('action_type') or data.get('action') or '').strip().lower()
    if action_type in ['request-info', 'request_info']:
        action_type = 'request_info'

    if not action_type or action_type not in VALID_REVIEW_ACTIONS:
        errors['action_type'] = f"Action type must be one of: {', '.join(sorted(VALID_REVIEW_ACTIONS))}"

    return len(errors) == 0, errors

