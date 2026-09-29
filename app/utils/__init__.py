"""
app/utils/__init__.py
Central export for AssureX utilities.
"""
from .hash_utils import compute_sha256, compute_bytes_sha256
from .date_utils import (
    compute_product_age_days,
    compute_remaining_warranty_days,
    is_within_reporting_period,
    parse_date_flexible,
)
from .file_handler import allowed_file, save_secure_upload
from .validators import (
    validate_email,
    validate_password_strength,
    validate_registration,
    validate_product_payload,
    validate_claim_payload,
    validate_reviewer_action_payload,
)
from .error_handlers import register_error_handlers

__all__ = [
    'compute_sha256',
    'compute_bytes_sha256',
    'compute_product_age_days',
    'compute_remaining_warranty_days',
    'is_within_reporting_period',
    'parse_date_flexible',
    'allowed_file',
    'save_secure_upload',
    'validate_email',
    'validate_password_strength',
    'validate_registration',
    'validate_product_payload',
    'validate_claim_payload',
    'validate_reviewer_action_payload',
    'register_error_handlers',
]
