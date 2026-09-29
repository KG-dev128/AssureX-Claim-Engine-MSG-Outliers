"""
app/models/models.py
All 16 SQLAlchemy Models for AssureX Claim Engine.
Strictly matching SRS Functional Requirements & Architecture Blueprint.
Compatible with NeonDB PostgreSQL and SQLite.
"""
import uuid
from datetime import datetime, date
from app.extensions import db


def generate_uuid():
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# 1. User Model (FR i, ii)
# ─────────────────────────────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = 'users'

    user_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default='customer')  # customer, service_employee, reviewer, admin
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    failed_login_count = db.Column(db.Integer, default=0, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    profile = db.relationship('UserProfile', backref='user', uselist=False, cascade='all, delete-orphan')
    products = db.relationship('Product', backref='owner', lazy='dynamic', cascade='all, delete-orphan')
    claims = db.relationship('Claim', backref='claimant', lazy='dynamic', cascade='all, delete-orphan')
    documents = db.relationship('Document', backref='uploader', lazy='dynamic')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    reviewer_actions = db.relationship('ReviewerAction', backref='reviewer', lazy='dynamic')
    audit_trails = db.relationship('AuditTrail', backref='user', lazy='dynamic')

    def to_dict(self, include_sensitive=False):
        data = {
            'user_id': self.user_id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'is_active': self.is_active,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if self.profile:
            data['profile'] = self.profile.to_dict()
        return data


# ─────────────────────────────────────────────────────────────────────────────
# 2. UserProfile Model (FR ii)
# ─────────────────────────────────────────────────────────────────────────────
class UserProfile(db.Model):
    __tablename__ = 'user_profiles'

    profile_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.user_id', ondelete='CASCADE'), unique=True, nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=True)
    organization = db.Column(db.String(150), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'profile_id': self.profile_id,
            'user_id': self.user_id,
            'full_name': self.full_name,
            'phone': self.phone,
            'address': self.address,
            'organization': self.organization,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Product Model (FR iii)
# ─────────────────────────────────────────────────────────────────────────────
class Product(db.Model):
    __tablename__ = 'products'

    product_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    product_name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(80), nullable=False)  # electronics, appliances, automotive, general
    brand = db.Column(db.String(100), nullable=False)
    model_number = db.Column(db.String(100), nullable=False)
    serial_number = db.Column(db.String(150), nullable=False, index=True)
    purchase_date = db.Column(db.Date, nullable=False)
    purchase_price = db.Column(db.Numeric(12, 2), nullable=True)
    retailer = db.Column(db.String(150), nullable=True)
    warranty_duration_months = db.Column(db.Integer, nullable=False, default=12)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    warranties = db.relationship('Warranty', backref='product', lazy='dynamic', cascade='all, delete-orphan')
    claims = db.relationship('Claim', backref='product', lazy='dynamic', cascade='all, delete-orphan')
    documents = db.relationship('Document', backref='product', lazy='dynamic')
    repairs = db.relationship('RepairHistory', backref='product', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        w = self.warranties.first()
        return {
            'product_id': self.product_id,
            'user_id': self.user_id,
            'product_name': self.product_name,
            'category': self.category,
            'brand': self.brand,
            'model_number': self.model_number,
            'serial_number': self.serial_number,
            'purchase_date': self.purchase_date.isoformat() if self.purchase_date else None,
            'purchase_price': float(self.purchase_price) if self.purchase_price is not None else None,
            'retailer': self.retailer,
            'warranty_duration_months': self.warranty_duration_months,
            'warranty': {
                'warranty_id': w.warranty_id if w else None,
                'start_date': w.start_date.isoformat() if w and w.start_date else None,
                'expiry_date': w.expiry_date.isoformat() if w and w.expiry_date else None,
                'is_active': w.is_active if w else False,
                'remaining_days': w.remaining_days if w else 0,
            } if w else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Warranty Model (FR iv, viii, ix)
# ─────────────────────────────────────────────────────────────────────────────
class Warranty(db.Model):
    __tablename__ = 'warranties'

    warranty_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    product_id = db.Column(db.String(36), db.ForeignKey('products.product_id', ondelete='CASCADE'), nullable=False, index=True)
    warranty_type = db.Column(db.String(30), nullable=False, default='standard')  # standard, extended
    provider = db.Column(db.String(150), nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date, nullable=False, index=True)
    coverage_conditions = db.Column(db.Text, nullable=True)
    exclusions = db.Column(db.Text, nullable=True)
    service_center_details = db.Column(db.Text, nullable=True)
    alert_days_before = db.Column(db.Integer, default=30, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    claims = db.relationship('Claim', backref='warranty', lazy='dynamic')

    @property
    def is_active(self):
        return self.expiry_date >= date.today()

    @property
    def remaining_days(self):
        return (self.expiry_date - date.today()).days

    def to_dict(self):
        return {
            'warranty_id': self.warranty_id,
            'product_id': self.product_id,
            'warranty_type': self.warranty_type,
            'provider': self.provider,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'expiry_date': self.expiry_date.isoformat() if self.expiry_date else None,
            'coverage_conditions': self.coverage_conditions,
            'exclusions': self.exclusions,
            'service_center_details': self.service_center_details,
            'alert_days_before': self.alert_days_before,
            'is_active': self.is_active,
            'remaining_days': self.remaining_days,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Document Model (FR v, vi, vii, xii, xiv, xxxi)
# ─────────────────────────────────────────────────────────────────────────────
class Document(db.Model):
    __tablename__ = 'documents'

    doc_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = db.Column(db.String(36), db.ForeignKey('products.product_id', ondelete='SET NULL'), nullable=True, index=True)
    claim_id = db.Column(db.String(36), db.ForeignKey('claims.claim_id', ondelete='SET NULL'), nullable=True, index=True)
    doc_type = db.Column(db.String(50), nullable=False)  # receipt, invoice, warranty_card, product_image, fault_evidence, repair_report, claim_summary_card, other
    file_name = db.Column(db.String(255), nullable=True)
    file_path = db.Column(db.String(500), nullable=False)
    file_hash = db.Column(db.String(64), nullable=False, index=True)  # SHA-256
    file_size = db.Column(db.BigInteger, nullable=True)
    mime_type = db.Column(db.String(80), nullable=True)
    ocr_extracted_data = db.Column(db.JSON, nullable=True)
    ocr_status = db.Column(db.String(20), default='pending', nullable=False)  # pending, processing, completed, failed
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'doc_id': self.doc_id,
            'user_id': self.user_id,
            'product_id': self.product_id,
            'claim_id': self.claim_id,
            'doc_type': self.doc_type,
            'file_name': self.file_name,
            'file_path': self.file_path,
            'file_hash': self.file_hash,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'ocr_extracted_data': self.ocr_extracted_data,
            'ocr_status': self.ocr_status,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Claim Model (FR x, xi, xxxviii)
# ─────────────────────────────────────────────────────────────────────────────
class Claim(db.Model):
    __tablename__ = 'claims'

    claim_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = db.Column(db.String(36), db.ForeignKey('products.product_id', ondelete='CASCADE'), nullable=False, index=True)
    warranty_id = db.Column(db.String(36), db.ForeignKey('warranties.warranty_id', ondelete='CASCADE'), nullable=False, index=True)
    product_age_days = db.Column(db.Integer, nullable=True)
    fault_occurrence_date = db.Column(db.Date, nullable=False)
    fault_description = db.Column(db.Text, nullable=False)
    damage_type = db.Column(db.String(100), nullable=True)  # electrical_failure, mechanical_failure, screen_crack, water_damage, wear_and_tear, battery_degradation
    warranty_conditions_met = db.Column(db.Boolean, default=True, nullable=False)
    previous_replacement = db.Column(db.Boolean, default=False, nullable=False)
    claim_submission_date = db.Column(db.Date, default=date.today, nullable=False)
    status = db.Column(db.String(40), default='draft', nullable=False, index=True)  # draft, submitted, under_evaluation, additional_info_required, manual_review, approved, rejected, closed
    missing_doc_count = db.Column(db.Integer, default=0, nullable=False)
    contradiction_count = db.Column(db.Integer, default=0, nullable=False)
    is_duplicate = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    documents = db.relationship('Document', backref='claim', lazy='dynamic')
    repairs = db.relationship('RepairHistory', backref='claim', lazy='dynamic')
    predictions = db.relationship('ModelPrediction', backref='claim', lazy='dynamic', cascade='all, delete-orphan')
    rule_results = db.relationship('RuleValidationResult', backref='claim', lazy='dynamic', cascade='all, delete-orphan')
    decision = db.relationship('ClaimDecision', backref='claim', uselist=False, cascade='all, delete-orphan')
    reviewer_actions = db.relationship('ReviewerAction', backref='claim', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'claim_id': self.claim_id,
            'user_id': self.user_id,
            'product_id': self.product_id,
            'warranty_id': self.warranty_id,
            'product_age_days': self.product_age_days,
            'fault_occurrence_date': self.fault_occurrence_date.isoformat() if self.fault_occurrence_date else None,
            'fault_description': self.fault_description,
            'damage_type': self.damage_type,
            'warranty_conditions_met': self.warranty_conditions_met,
            'previous_replacement': self.previous_replacement,
            'claim_submission_date': self.claim_submission_date.isoformat() if self.claim_submission_date else None,
            'status': self.status,
            'missing_doc_count': self.missing_doc_count,
            'contradiction_count': self.contradiction_count,
            'is_duplicate': self.is_duplicate,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 7. RepairHistory Model (FR xiii)
# ─────────────────────────────────────────────────────────────────────────────
class RepairHistory(db.Model):
    __tablename__ = 'repair_history'

    repair_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    product_id = db.Column(db.String(36), db.ForeignKey('products.product_id', ondelete='CASCADE'), nullable=False, index=True)
    claim_id = db.Column(db.String(36), db.ForeignKey('claims.claim_id', ondelete='SET NULL'), nullable=True, index=True)
    repair_date = db.Column(db.Date, nullable=False)
    repair_center = db.Column(db.String(200), nullable=True)
    is_authorized = db.Column(db.Boolean, default=True, nullable=False)
    replaced_parts = db.Column(db.Text, nullable=True)
    repair_outcome = db.Column(db.String(100), nullable=True)
    repair_cost = db.Column(db.Numeric(10, 2), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'repair_id': self.repair_id,
            'product_id': self.product_id,
            'claim_id': self.claim_id,
            'repair_date': self.repair_date.isoformat() if self.repair_date else None,
            'repair_center': self.repair_center,
            'is_authorized': self.is_authorized,
            'replaced_parts': self.replaced_parts,
            'repair_outcome': self.repair_outcome,
            'repair_cost': float(self.repair_cost) if self.repair_cost is not None else None,
            'notes': self.notes,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 8. ModelVersion Model (FR xlviii)
# ─────────────────────────────────────────────────────────────────────────────
class ModelVersion(db.Model):
    __tablename__ = 'model_versions'

    version_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    model_type = db.Column(db.String(30), nullable=False)  # python, gtm
    version_tag = db.Column(db.String(50), nullable=False)
    algorithm = db.Column(db.String(100), nullable=True)
    accuracy = db.Column(db.Numeric(5, 4), nullable=True)
    f1_score = db.Column(db.Numeric(5, 4), nullable=True)
    trained_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    model_file_path = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    predictions = db.relationship('ModelPrediction', backref='model_version', lazy='dynamic')

    def to_dict(self):
        return {
            'version_id': self.version_id,
            'model_type': self.model_type,
            'version_tag': self.version_tag,
            'algorithm': self.algorithm,
            'accuracy': float(self.accuracy) if self.accuracy is not None else None,
            'f1_score': float(self.f1_score) if self.f1_score is not None else None,
            'trained_at': self.trained_at.isoformat() if self.trained_at else None,
            'model_file_path': self.model_file_path,
            'is_active': self.is_active,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 9. ModelPrediction Model (FR xviii, xix, xxi)
# ─────────────────────────────────────────────────────────────────────────────
class ModelPrediction(db.Model):
    __tablename__ = 'model_predictions'

    prediction_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    claim_id = db.Column(db.String(36), db.ForeignKey('claims.claim_id', ondelete='CASCADE'), nullable=False, index=True)
    model_type = db.Column(db.String(20), nullable=False)  # python, gtm
    model_version_id = db.Column(db.String(36), db.ForeignKey('model_versions.version_id', ondelete='SET NULL'), nullable=True)
    predicted_class = db.Column(db.String(30), nullable=False)  # valid, invalid, manual_review
    confidence_valid = db.Column(db.Numeric(5, 4), nullable=True)
    confidence_invalid = db.Column(db.Numeric(5, 4), nullable=True)
    confidence_manual_review = db.Column(db.Numeric(5, 4), nullable=True)
    raw_input_features = db.Column(db.JSON, nullable=True)
    predicted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'prediction_id': self.prediction_id,
            'claim_id': self.claim_id,
            'model_type': self.model_type,
            'model_version_id': self.model_version_id,
            'predicted_class': self.predicted_class,
            'confidence_valid': float(self.confidence_valid) if self.confidence_valid is not None else None,
            'confidence_invalid': float(self.confidence_invalid) if self.confidence_invalid is not None else None,
            'confidence_manual_review': float(self.confidence_manual_review) if self.confidence_manual_review is not None else None,
            'raw_input_features': self.raw_input_features,
            'predicted_at': self.predicted_at.isoformat() if self.predicted_at else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 10. RuleValidationResult Model (FR xxv)
# ─────────────────────────────────────────────────────────────────────────────
class RuleValidationResult(db.Model):
    __tablename__ = 'rule_validation_results'

    rule_result_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    claim_id = db.Column(db.String(36), db.ForeignKey('claims.claim_id', ondelete='CASCADE'), nullable=False, index=True)
    rule_name = db.Column(db.String(100), nullable=False)
    rule_passed = db.Column(db.Boolean, nullable=False)
    details = db.Column(db.Text, nullable=True)
    evaluated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'rule_result_id': self.rule_result_id,
            'claim_id': self.claim_id,
            'rule_name': self.rule_name,
            'rule_passed': self.rule_passed,
            'details': self.details,
            'evaluated_at': self.evaluated_at.isoformat() if self.evaluated_at else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 11. ClaimDecision Model (FR xxxiv, xxxv)
# ─────────────────────────────────────────────────────────────────────────────
class ClaimDecision(db.Model):
    __tablename__ = 'claim_decisions'

    decision_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    claim_id = db.Column(db.String(36), db.ForeignKey('claims.claim_id', ondelete='CASCADE'), unique=True, nullable=False)
    python_predicted_class = db.Column(db.String(30), nullable=True)
    python_top_confidence = db.Column(db.Numeric(5, 4), nullable=True)
    gtm_predicted_class = db.Column(db.String(30), nullable=True)
    gtm_top_confidence = db.Column(db.Numeric(5, 4), nullable=True)
    confidence_difference = db.Column(db.Numeric(5, 4), nullable=True)
    consistency_status = db.Column(db.String(30), nullable=True)  # strong_match, acceptable_match, weak_match, model_disagreement, uncertain_result
    rules_passed_count = db.Column(db.Integer, default=0, nullable=False)
    rules_failed_count = db.Column(db.Integer, default=0, nullable=False)
    missing_doc_count = db.Column(db.Integer, default=0, nullable=False)
    contradiction_count = db.Column(db.Integer, default=0, nullable=False)
    is_duplicate = db.Column(db.Boolean, default=False, nullable=False)
    final_decision = db.Column(db.String(30), nullable=False)  # likely_valid, likely_invalid, manual_review_required
    decision_explanation = db.Column(db.JSON, nullable=True)
    decided_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'decision_id': self.decision_id,
            'claim_id': self.claim_id,
            'python_predicted_class': self.python_predicted_class,
            'python_top_confidence': float(self.python_top_confidence) if self.python_top_confidence is not None else None,
            'gtm_predicted_class': self.gtm_predicted_class,
            'gtm_top_confidence': float(self.gtm_top_confidence) if self.gtm_top_confidence is not None else None,
            'confidence_difference': float(self.confidence_difference) if self.confidence_difference is not None else None,
            'consistency_status': self.consistency_status,
            'rules_passed_count': self.rules_passed_count,
            'rules_failed_count': self.rules_failed_count,
            'missing_doc_count': self.missing_doc_count,
            'contradiction_count': self.contradiction_count,
            'is_duplicate': self.is_duplicate,
            'final_decision': self.final_decision,
            'decision_explanation': self.decision_explanation,
            'decided_at': self.decided_at.isoformat() if self.decided_at else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 12. ReviewerAction Model (FR xxxvi, xxxvii)
# ─────────────────────────────────────────────────────────────────────────────
class ReviewerAction(db.Model):
    __tablename__ = 'reviewer_actions'

    action_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    claim_id = db.Column(db.String(36), db.ForeignKey('claims.claim_id', ondelete='CASCADE'), nullable=False, index=True)
    reviewer_id = db.Column(db.String(36), db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    action_type = db.Column(db.String(30), nullable=False)  # approve, reject, request_info, override
    override_decision = db.Column(db.String(30), nullable=True)  # approved, rejected
    comments = db.Column(db.Text, nullable=True)
    acted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'action_id': self.action_id,
            'claim_id': self.claim_id,
            'reviewer_id': self.reviewer_id,
            'action_type': self.action_type,
            'override_decision': self.override_decision,
            'comments': self.comments,
            'acted_at': self.acted_at.isoformat() if self.acted_at else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 13. Notification Model (FR ix, xxxix)
# ─────────────────────────────────────────────────────────────────────────────
class Notification(db.Model):
    __tablename__ = 'notifications'

    notification_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False, index=True)
    type = db.Column(db.String(60), nullable=False)  # warranty_expiry, claim_status_change, missing_documents, anomaly_alert
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    related_claim_id = db.Column(db.String(36), nullable=True)
    related_product_id = db.Column(db.String(36), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'notification_id': self.notification_id,
            'user_id': self.user_id,
            'type': self.type,
            'message': self.message,
            'is_read': self.is_read,
            'related_claim_id': self.related_claim_id,
            'related_product_id': self.related_product_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 14. AuditTrail Model (FR xlvii)
# ─────────────────────────────────────────────────────────────────────────────
class AuditTrail(db.Model):
    __tablename__ = 'audit_trail'

    audit_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.user_id', ondelete='SET NULL'), nullable=True, index=True)
    action_type = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(50), nullable=True)  # user, product, warranty, claim, document, decision
    entity_id = db.Column(db.String(36), nullable=True, index=True)
    details = db.Column(db.JSON, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'audit_id': self.audit_id,
            'user_id': self.user_id,
            'action_type': self.action_type,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'details': self.details,
            'ip_address': self.ip_address,
            'occurred_at': self.occurred_at.isoformat() if self.occurred_at else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 15. WarrantyPolicy Model (FR xxvi)
# ─────────────────────────────────────────────────────────────────────────────
class WarrantyPolicy(db.Model):
    __tablename__ = 'warranty_policies'

    policy_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    product_category = db.Column(db.String(80), unique=True, nullable=False, index=True)
    policy_data = db.Column(db.JSON, nullable=False)
    version = db.Column(db.String(20), default='1.0', nullable=False)
    updated_by = db.Column(db.String(36), db.ForeignKey('users.user_id', ondelete='SET NULL'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'policy_id': self.policy_id,
            'product_category': self.product_category,
            'policy_data': self.policy_data,
            'version': self.version,
            'updated_by': self.updated_by,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 16. AnomalyAlert Model (FR l)
# ─────────────────────────────────────────────────────────────────────────────
class AnomalyAlert(db.Model):
    __tablename__ = 'anomaly_alerts'

    alert_id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    alert_type = db.Column(db.String(80), nullable=False)  # multiple_failed_logins, duplicate_claim_surge, high_fraud_score
    severity = db.Column(db.String(20), nullable=False)  # low, medium, high, critical
    message = db.Column(db.Text, nullable=True)
    related_user_id = db.Column(db.String(36), nullable=True)
    related_claim_id = db.Column(db.String(36), nullable=True)
    is_resolved = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'alert_id': self.alert_id,
            'alert_type': self.alert_type,
            'severity': self.severity,
            'message': self.message,
            'related_user_id': self.related_user_id,
            'related_claim_id': self.related_claim_id,
            'is_resolved': self.is_resolved,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
