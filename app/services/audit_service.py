"""
app/services/audit_service.py
Centralized immutable audit trail logging (FR xlvii).
Records all system events with user, timestamp, IP, entity reference, and metadata.
"""
from typing import Optional, Dict, Any
from app.extensions import db
from app.models import AuditTrail


def log_action(
    action_type: str,
    user_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> AuditTrail:
    """
    Log an event to the audit_trail table.
    """
    try:
        audit = AuditTrail(
            user_id=user_id,
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
            ip_address=ip_address,
        )
        db.session.add(audit)
        db.session.commit()
        return audit
    except Exception as e:
        db.session.rollback()
        # Even if audit logging encounters a transient issue, log to stderr but don't crash main operation
        print(f"[AuditService Error] Failed to write audit record: {e}")
        return None
