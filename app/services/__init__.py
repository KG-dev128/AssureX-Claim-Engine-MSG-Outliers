"""
app/services/__init__.py
Central service layer export for AssureX Claim Engine.
"""
from .auth_service import (
    hash_password,
    check_password,
    register_user,
    login_user,
    logout_user,
    role_required,
)
from .audit_service import log_action
from .notification_service import (
    create_notification,
    get_user_notifications,
    mark_notification_read,
    mark_all_notifications_read,
    check_warranty_expiry_alerts,
    notify_claim_status_change,
    notify_missing_documents,
)
from .policy_service import (
    load_policy,
    seed_default_policies,
    update_policy,
    list_all_policies,
)
from .ocr_service import (
    extract_raw_text,
    parse_ocr_fields,
    run_ocr_for_document,
)
from .preprocessing_service import (
    build_feature_dict,
    build_feature_vector,
)
from .card_generator import generate_claim_summary_card
from .duplicate_detector import detect_duplicate_claim, is_file_hash_duplicate
from .contradiction_detector import detect_contradictions
from .rule_engine import evaluate_warranty_rules
from .ml_service import predict_claim
from .gtm_service import predict_gtm
from .decision_engine import evaluate_final_decision
from .report_generator import generate_claim_pdf_report, generate_claims_csv

__all__ = [
    'hash_password',
    'check_password',
    'register_user',
    'login_user',
    'logout_user',
    'role_required',
    'log_action',
    'create_notification',
    'get_user_notifications',
    'mark_notification_read',
    'mark_all_notifications_read',
    'check_warranty_expiry_alerts',
    'notify_claim_status_change',
    'notify_missing_documents',
    'load_policy',
    'seed_default_policies',
    'update_policy',
    'list_all_policies',
    'extract_raw_text',
    'parse_ocr_fields',
    'run_ocr_for_document',
    'build_feature_dict',
    'build_feature_vector',
    'generate_claim_summary_card',
    'detect_duplicate_claim',
    'is_file_hash_duplicate',
    'detect_contradictions',
    'evaluate_warranty_rules',
    'predict_claim',
    'predict_gtm',
    'evaluate_final_decision',
    'generate_claim_pdf_report',
    'generate_claims_csv',
]
