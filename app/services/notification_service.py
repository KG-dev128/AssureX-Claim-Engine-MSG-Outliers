"""
app/services/notification_service.py
User notifications, warranty expiry alerts, and claim state tracking (FR ix, xxxix).
"""
from datetime import date, timedelta, datetime
from typing import List, Optional, Dict, Any
from app.extensions import db
from app.models import Notification, Warranty, Product, Claim


def create_notification(
    user_id: str,
    type: str,
    message: str,
    related_claim_id: Optional[str] = None,
    related_product_id: Optional[str] = None,
) -> Notification:
    """Create a persistent user notification."""
    notif = Notification(
        user_id=user_id,
        type=type,
        message=message,
        related_claim_id=related_claim_id,
        related_product_id=related_product_id,
        is_read=False,
    )
    db.session.add(notif)
    db.session.commit()
    return notif


def get_user_notifications(user_id: str, unread_only: bool = False, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve notifications for a user."""
    query = Notification.query.filter_by(user_id=user_id)
    if unread_only:
        query = query.filter_by(is_read=False)
    records = query.order_by(Notification.created_at.desc()).limit(limit).all()
    return [r.to_dict() for r in records]


def mark_notification_read(notification_id: str, user_id: str) -> bool:
    """Mark a specific notification as read."""
    notif = Notification.query.filter_by(notification_id=notification_id, user_id=user_id).first()
    if notif:
        notif.is_read = True
        db.session.commit()
        return True
    return False


def mark_all_notifications_read(user_id: str) -> int:
    """Mark all unread notifications for a user as read."""
    unread = Notification.query.filter_by(user_id=user_id, is_read=False).all()
    count = len(unread)
    for n in unread:
        n.is_read = True
    db.session.commit()
    return count


def check_warranty_expiry_alerts() -> int:
    """
    Find warranties nearing expiration and issue notifications to their owners (FR ix).
    Runs against alert_days_before threshold.
    """
    today = date.today()
    warranties = Warranty.query.filter(Warranty.expiry_date >= today).all()
    created_count = 0

    for w in warranties:
        days_left = (w.expiry_date - today).days
        if days_left <= w.alert_days_before:
            product = Product.query.get(w.product_id)
            if not product:
                continue

            # Prevent duplicate notifications on the same day
            existing = Notification.query.filter_by(
                user_id=product.user_id,
                related_product_id=product.product_id,
                type='warranty_expiry'
            ).filter(Notification.created_at >= datetime.utcnow() - timedelta(days=7)).first()

            if not existing:
                create_notification(
                    user_id=product.user_id,
                    type='warranty_expiry',
                    message=f"Warranty for '{product.product_name}' expires in {days_left} days ({w.expiry_date}).",
                    related_product_id=product.product_id,
                )
                created_count += 1

    return created_count


def notify_claim_status_change(claim_id: str, new_status: str, user_id: str):
    """Notify user of an updated claim status."""
    message = f"Your claim #{claim_id[:8].upper()} status is now: {new_status.replace('_', ' ').title()}."
    return create_notification(
        user_id=user_id,
        type='claim_status_change',
        message=message,
        related_claim_id=claim_id
    )


def notify_missing_documents(claim_id: str, missing_docs: List[str], user_id: str):
    """Notify user of required missing documents."""
    doc_str = ', '.join([d.replace('_', ' ').title() for d in missing_docs])
    message = f"Additional documents required for claim #{claim_id[:8].upper()}: {doc_str}."
    return create_notification(
        user_id=user_id,
        type='missing_documents',
        message=message,
        related_claim_id=claim_id
    )
