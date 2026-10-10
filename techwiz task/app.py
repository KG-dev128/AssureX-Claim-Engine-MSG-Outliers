"""
ClaimSure_AI / AssureX — Unified Flask Application
Integrates the complete frontend with the 10-step claim engine backend.
"""

from __future__ import annotations

import hashlib
import io
import base64
import hmac
import importlib
import json
import mimetypes
import os
import secrets
import re
import math
import shutil
from difflib import SequenceMatcher
import threading
import zipfile
import time
from threading import RLock
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException
import sqlite3
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

warnings.filterwarnings("ignore")

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template_string,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)

# -----------------------------------------------------------------------------
# Configuration & Paths
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "Frontend"
ASSETS_DIR = FRONTEND_DIR / "assets"
DATA_DIR = Path(os.environ.get("ASSUREX_DATA_DIR", BASE_DIR / "instance"))
CLAIMS_DIR = DATA_DIR / "claims"
OUTPUTS_DIR = DATA_DIR / "outputs"
POLICIES_DIR = BASE_DIR / "policies"
MODELS_DIR = BASE_DIR / "models"
DB_PATH = DATA_DIR / "assurex.db"
HASH_REGISTRY_PATH = DATA_DIR / "document_hash_registry.json"
AUDIT_TRAIL_PATH = DATA_DIR / "audit_trail.jsonl"
CLAIM_DOCUMENT_TYPES = {"purchase_receipt", "warranty_card", "fault_evidence", "product_image",
                        "serial_number_evidence", "repair_report", "fault_video"}

for directory in [DATA_DIR, CLAIMS_DIR, OUTPUTS_DIR, POLICIES_DIR, MODELS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

app = Flask(
    __name__,
    static_folder=str(ASSETS_DIR),
    static_url_path="/assets",
)
secret_path = DATA_DIR / ".session-key"
if not secret_path.exists():
    secret_path.write_text(secrets.token_hex(32), encoding="utf-8")
app.secret_key = os.environ.get("SECRET_KEY") or secret_path.read_text(encoding="utf-8")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
app.config.update(JWT_COOKIE_NAME="assurex_token", JWT_TTL_SECONDS=8 * 60 * 60,
                  SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
                  JWT_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1")
evaluation_lock = RLock()
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB upload limit

# -----------------------------------------------------------------------------
# Dynamic Import of 10-Step Engine Modules
# -----------------------------------------------------------------------------
step01 = importlib.import_module("01_account_login_product")
step03 = importlib.import_module("03_document_fingerprint")
step04 = importlib.import_module("04_receipt_ocr")
step06 = importlib.import_module("06_ai_paths")
step07 = importlib.import_module("07_compare_models")
step08 = importlib.import_module("08_warranty_rule_engine")
step09 = importlib.import_module("09_final_master_decision")
step10 = importlib.import_module("10_manual_review_and_pdf")


# -----------------------------------------------------------------------------
# Database Setup & Initialization
# -----------------------------------------------------------------------------
def init_app_database() -> None:
    """Initialize an empty store for real accounts and submissions."""
    step01.DB_PATH = DATA_DIR / "assurex.db"
    step03.REGISTRY_PATH = HASH_REGISTRY_PATH
    step10.AUDIT_PATH = AUDIT_TRAIL_PATH
    step01.create_tables()
    # Real accounts only; no demo seeding.

    with step01.get_db() as db:
        db.execute("UPDATE users SET role = 'user' WHERE role = 'customer'")
        db.execute("CREATE TABLE IF NOT EXISTS revoked_tokens (jti TEXT PRIMARY KEY, expires_at INTEGER NOT NULL)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS claims (
                claim_id TEXT PRIMARY KEY,
                user_id TEXT,
                product_id TEXT,
                category TEXT NOT NULL,
                claim_title TEXT,
                purchase_date TEXT,
                fault_description TEXT,
                invoice_number TEXT,
                store_name TEXT,
                serial_number TEXT,
                paid_amount TEXT,
                warranty_months INTEGER DEFAULT 24,
                unauthorized_repair INTEGER DEFAULT 0,
                repair_center TEXT,
                fault_date TEXT,
                status TEXT NOT NULL,
                status_stage TEXT DEFAULT 'Draft',
                decision TEXT,
                automated_decision TEXT,
                confidence REAL,
                explanation TEXT,
                certificate_path TEXT,
                reviewer_comment TEXT,
                reviewer_override TEXT,
                model_version TEXT,
                duplicate_flag INTEGER DEFAULT 0,
                model_consistency TEXT,
                risk_level TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
            """
        )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(claims)").fetchall()}
        if "product_id" not in columns:
            db.execute("ALTER TABLE claims ADD COLUMN product_id TEXT")
        if "duplicate_flag" not in columns:
            db.execute("ALTER TABLE claims ADD COLUMN duplicate_flag INTEGER DEFAULT 0")
        if "model_consistency" not in columns:
            db.execute("ALTER TABLE claims ADD COLUMN model_consistency TEXT")
        if "automated_decision" not in columns:
            db.execute("ALTER TABLE claims ADD COLUMN automated_decision TEXT")
        if "risk_level" not in columns:
            db.execute("ALTER TABLE claims ADD COLUMN risk_level TEXT")
        if "image_model_version" not in columns:
            db.execute("ALTER TABLE claims ADD COLUMN image_model_version TEXT")
        if "intake_actor_id" not in columns:
            db.execute("ALTER TABLE claims ADD COLUMN intake_actor_id TEXT")
        db.execute("CREATE INDEX IF NOT EXISTS idx_claims_product_id ON claims(product_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_claims_status_stage ON claims(status_stage)")
        db.execute("""CREATE TABLE IF NOT EXISTS warranties (
            warranty_id TEXT PRIMARY KEY, product_id TEXT NOT NULL, user_id TEXT NOT NULL,
            provider TEXT NOT NULL, start_date TEXT NOT NULL, expiry_date TEXT NOT NULL,
            coverage TEXT NOT NULL, exclusions TEXT NOT NULL DEFAULT '', is_extended INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, FOREIGN KEY(product_id) REFERENCES products(product_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS repairs (
            repair_id TEXT PRIMARY KEY, product_id TEXT NOT NULL, user_id TEXT NOT NULL,
            repair_date TEXT NOT NULL, service_center TEXT NOT NULL, parts_replaced TEXT NOT NULL DEFAULT '',
            outcome TEXT NOT NULL, cost REAL NOT NULL DEFAULT 0, authorized INTEGER NOT NULL DEFAULT 0,
            report_path TEXT, created_at TEXT NOT NULL, FOREIGN KEY(product_id) REFERENCES products(product_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS claim_events (
            event_id TEXT PRIMARY KEY, claim_id TEXT NOT NULL, user_id TEXT NOT NULL,
            event_type TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS application_audit_events (
            event_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL, event_type TEXT NOT NULL, details TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS prediction_records (
            claim_id TEXT PRIMARY KEY, python_result TEXT, image_result TEXT, comparison TEXT,
            rule_results TEXT, final_decision TEXT, model_version TEXT, created_at TEXT NOT NULL)""")
        db.execute("CREATE TABLE IF NOT EXISTS application_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL)")
        db.execute("""CREATE TABLE IF NOT EXISTS anomaly_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, severity TEXT NOT NULL,
            actor_id TEXT, entity_id TEXT, details TEXT NOT NULL, created_at TEXT NOT NULL,
            acknowledged_at TEXT, acknowledged_by TEXT)""")
        db.execute("INSERT OR IGNORE INTO application_settings(setting_key,setting_value) VALUES ('warranty_expiry_lead_days','30')")
        # Notifications table
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                claim_id TEXT,
                message TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        user_columns = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
        if "phone" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
        warranty_columns = {row["name"] for row in db.execute("PRAGMA table_info(warranties)").fetchall()}
        if "service_center_details" not in warranty_columns:
            db.execute("ALTER TABLE warranties ADD COLUMN service_center_details TEXT NOT NULL DEFAULT ''")
        prediction_columns = {row["name"] for row in db.execute("PRAGMA table_info(prediction_records)").fetchall()}
        if "image_model_version" not in prediction_columns:
            db.execute("ALTER TABLE prediction_records ADD COLUMN image_model_version TEXT")
        db.commit()


# ---------------------------------------------------------------------------
# Shared EasyOCR reader (cached at module level – avoids reloading model)
# ---------------------------------------------------------------------------
_easyocr_reader = None

def get_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        try:
            import easyocr, warnings
            warnings.filterwarnings("ignore")
            _easyocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        except (ImportError, OSError, RuntimeError):
            app.logger.exception("EasyOCR is unavailable; the configured OCR fallback may still be used.")
    return _easyocr_reader


init_app_database()
# OCR initializes lazily when a document is submitted.


# -----------------------------------------------------------------------------
# CORS & Request Lifecycle Handling
# -----------------------------------------------------------------------------
@app.after_request
def add_cors_headers(response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
def get_current_user() -> Dict[str, Any]:
    """Validate the signed JWT and reload the account's current role."""
    token = request.cookies.get(app.config["JWT_COOKIE_NAME"], "")
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    try:
        header, payload, signature = token.split(".")
        header_data = json.loads(_b64decode(header))
        if header_data.get("alg") != "HS256" or header_data.get("typ") != "JWT":
            raise ValueError("algorithm")
        signed = f"{header}.{payload}".encode("ascii")
        expected = hmac.new(app.secret_key.encode(), signed, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64decode(signature)):
            raise ValueError("signature")
        claims = json.loads(_b64decode(payload))
        if claims.get("iss") != "assurex" or int(claims.get("exp", 0)) <= int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("expiry")
        with step01.get_db() as db:
            if not claims.get("jti") or db.execute("SELECT 1 FROM revoked_tokens WHERE jti = ?", (claims["jti"],)).fetchone():
                raise ValueError("revoked")
            row = db.execute("SELECT * FROM users WHERE user_id = ?", (claims.get("sub"),)).fetchone()
            if row and row["role"] == claims.get("role") and row["role"] in {"user", "admin", "reviewer", "service_center"}:
                return dict(row)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        pass
    abort(401, description="Sign in to continue.")


def get_optional_user() -> Optional[Dict[str, Any]]:
    """Return the authenticated account when present; public pages may remain anonymous."""
    try:
        return get_current_user()
    except HTTPException as error:
        if error.code == 401:
            return None
        raise


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_access_token(user: Dict[str, Any]) -> str:
    now = int(datetime.now(timezone.utc).timestamp())
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64encode(json.dumps({"iss": "assurex", "sub": user["user_id"], "role": user["role"],
                                    "iat": now, "exp": now + app.config["JWT_TTL_SECONDS"],
                                    "jti": secrets.token_urlsafe(18)}, separators=(",", ":")).encode())
    signed = f"{header}.{payload}"
    signature = _b64encode(hmac.new(app.secret_key.encode(), signed.encode("ascii"), hashlib.sha256).digest())
    return f"{signed}.{signature}"


def role_dashboard(role: str) -> str:
    return {"user": "/user-profile.html", "admin": "/admin.html", "reviewer": "/reviewer.html",
            "service_center": "/service-center-dashboard.html"}.get(role, "/login.html")


def set_auth_cookie(response, user: Dict[str, Any]):
    response.set_cookie(app.config["JWT_COOKIE_NAME"], create_access_token(user),
                        httponly=True, secure=app.config["JWT_COOKIE_SECURE"], samesite="Strict",
                        max_age=app.config["JWT_TTL_SECONDS"], path="/")
    return response


def require_role(*allowed_roles: str):
    """Server-side role guard. Returns error response or None."""
    user = get_current_user()
    role = user.get("role", "customer")
    if role not in allowed_roles:
        return jsonify({"success": False, "error": f"Access denied. Required role: {', '.join(allowed_roles)}."}), 403
    return None


def push_notification(user_id: str, claim_id: str, message: str) -> None:
    """Insert an in-app notification row."""
    try:
        with step01.get_db() as db:
            db.execute(
                "INSERT INTO notifications (user_id, claim_id, message, created_at) VALUES (?, ?, ?, ?)",
                (user_id, claim_id, message, datetime.now(timezone.utc).isoformat()),
            )
            db.commit()
    except step01.DatabaseError:
        app.logger.exception("Could not persist notification for user %s", user_id)


# 8-stage status state machine
_STATUS_STAGES = [
    "Draft", "Submitted", "Under Evaluation",
    "Additional Info Required", "Manual Review",
    "Approved", "Rejected", "Closed"
]
_STATUS_TRANSITIONS = {
    "Draft": {"Submitted"},
    "Submitted": {"Under Evaluation"},
    "Under Evaluation": {"Additional Info Required", "Manual Review", "Approved", "Rejected"},
    "Additional Info Required": {"Submitted", "Additional Info Required", "Manual Review", "Approved", "Rejected", "Closed"},
    "Manual Review": {"Additional Info Required", "Manual Review", "Approved", "Rejected", "Closed"},
    "Approved": {"Closed"},
    "Rejected": {"Closed"},
    "Closed": set(),
}


def advance_claim_status(claim_id: str, new_stage: str, user_id: str = "") -> None:
    """Persist a new status stage to DB and push a notification."""
    if new_stage not in _STATUS_STAGES:
        return
    try:
        with step01.get_db() as db:
            current = db.execute("SELECT status_stage,user_id FROM claims WHERE claim_id=?", (claim_id,)).fetchone()
            if not current or new_stage not in _STATUS_TRANSITIONS.get(current["status_stage"], set()):
                app.logger.warning("Rejected illegal claim stage transition for %s: %s -> %s", claim_id, current["status_stage"] if current else "missing", new_stage)
                return
            user_id = user_id or current["user_id"]
            db.execute("UPDATE claims SET status_stage=?,updated_at=? WHERE claim_id=? AND status_stage=?",
                       (new_stage, datetime.now(timezone.utc).isoformat(), claim_id, current["status_stage"]))
            db.commit()
        if user_id:
            push_notification(user_id, claim_id, f"Your claim {claim_id} is now: {new_stage}")
            record_claim_event(claim_id, user_id, "status_changed", {"status_stage": new_stage})
            record_application_event(user_id, "claim", claim_id, "status_changed", {"status_stage": new_stage})
    except step01.DatabaseError:
        app.logger.exception("Could not advance claim stage for %s", claim_id)


def find_policy_for_category(category: str) -> Dict[str, Any]:
    """Load policy JSON for category safely."""
    category_normalized = category.strip().lower()
    name_map = {
        "laptop": "laptop_policy.json",
        "smartphone": "smartphone_policy.json",
        "tv": "television_policy.json",
        "television": "television_policy.json",
        "refrigerator": "refrigerator_policy.json",
        "ac": "ac_policy.json",
        "air conditioner": "ac_policy.json",
        "microwave": "microwave_policy.json",
        "washing machine": "washing_machine_policy.json",
        "printer": "printer_policy.json",
    }
    filename = name_map.get(category_normalized)
    if not filename:
        abort(400, description="Select a supported product category.")
    policy_path = POLICIES_DIR / filename
    if not policy_path.exists():
        policy_path = BASE_DIR / filename
    if policy_path.exists():
        return json.loads(policy_path.read_text(encoding="utf-8"))
    raise ValueError(f"No warranty policy configured for {category}")


def serialized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with evaluation_lock:
            return function(*args, **kwargs)
    return wrapped


def normalize_date(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(value), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_number(value, name, integer=False):
    try:
        result = float(str(value).replace(",", ""))
        if not math.isfinite(result) or result < 0 or (integer and not result.is_integer()):
            raise ValueError()
        return int(result) if integer else result
    except (ValueError, TypeError):
        abort(400, description=f"Enter a valid number for {name}.")


def parse_bool(value) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


@app.errorhandler(HTTPException)
def api_http_error(error):
    return jsonify(success=False, error=error.description), error.code


# -----------------------------------------------------------------------------
# Frontend Static Page Routes
# -----------------------------------------------------------------------------
@app.route("/")
@app.route("/index.html")
def route_home():
    return send_from_directory(FRONTEND_DIR, "index.html")


def serve_role_page(filename: str, required_role: str):
    try:
        user = get_current_user()
    except HTTPException:
        return redirect("/login.html")
    if user["role"] != required_role:
        return redirect(role_dashboard(user["role"]))
    return send_from_directory(FRONTEND_DIR, filename)


@app.route("/login.html")
def route_login_page():
    try:
        return redirect(role_dashboard(get_current_user()["role"]))
    except HTTPException:
        pass
    return send_from_directory(FRONTEND_DIR, "login.html")


@app.route("/register.html")
def route_register_page():
    try:
        return redirect(role_dashboard(get_current_user()["role"]))
    except HTTPException:
        pass
    return send_from_directory(FRONTEND_DIR, "register.html")


@app.route("/claim.html")
def route_claim_page():
    return serve_role_page("claim.html", "user")


@app.route("/user-profile.html")
def route_user_profile_page():
    return serve_role_page("user-profile.html", "user")


@app.route("/products.html")
def route_products_page():
    return serve_role_page("products.html", "user")


@app.route("/reviewer.html")
def route_reviewer_page():
    return serve_role_page("reviewer.html", "reviewer")


@app.route("/service-center-dashboard.html")
def route_service_center_page():
    return serve_role_page("service-center-dashboard.html", "service_center")


@app.route("/admin.html")
def route_admin_page():
    return serve_role_page("admin.html", "admin")


@app.route("/contact.html")
def route_contact_page():
    return send_from_directory(FRONTEND_DIR, "contact.html")


@app.route("/outputs/<path:filename>")
def route_outputs(filename: str):
    abort(404)


@app.route("/data/claims/<path:filename>")
def route_claim_file(filename: str):
    abort(404)


# -----------------------------------------------------------------------------
# Authentication & Account APIs
# -----------------------------------------------------------------------------
@app.route("/api/login", methods=["POST"])
@app.route("/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or request.form.to_dict()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required."}), 400

    user = step01.login(email, password)
    if not user:
        email_fingerprint = hashlib.sha256(email.encode("utf-8")).hexdigest()
        record_application_event("anonymous", "authentication", email_fingerprint, "login_failed", {"email_sha256": email_fingerprint})
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        with step01.get_db() as db:
            failures = db.execute("SELECT COUNT(*) AS n FROM anomaly_events WHERE event_type IN ('login_failure','repeated_login_failures') AND entity_id=? AND created_at>=?",
                                  (email_fingerprint, cutoff)).fetchone()["n"]
        if failures == 4 or (failures > 4 and failures % 5 == 4):
            record_anomaly("repeated_login_failures", "high", {"failed_attempts_last_15_minutes": failures + 1}, entity_id=email_fingerprint)
        else:
            record_anomaly("login_failure", "low", {"authentication": "failed"}, entity_id=email_fingerprint)
        return jsonify({"success": False, "error": "Invalid email or password."}), 401

    record_application_event(user["user_id"], "authentication", user["user_id"], "login_succeeded", {"role": user["role"]})

    redirect_target = role_dashboard("user" if user["role"] == "customer" else user["role"])
    if request.is_json:
        response = jsonify({
            "success": True,
            "access_token": create_access_token(user),
            "token_type": "Bearer",
            "expires_in": app.config["JWT_TTL_SECONDS"],
            "user": {
                "user_id": user["user_id"],
                "name": user["name"],
                "email": user["email"],
                "role": user["role"],
            },
            "redirect": redirect_target,
        })
        return set_auth_cookie(response, user)
    return set_auth_cookie(redirect(redirect_target), user)


@app.route("/api/register", methods=["POST"])
@app.route("/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or request.form.to_dict()
    name = data.get("name") or data.get("fullName", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not name or not email or not password:
        return jsonify({"success": False, "error": "Name, email, and password are required."}), 400
    if len(password) < 8:
        abort(400, description="Passwords must be at least 8 characters.")

    role = "user"  # Staff accounts are provisioned by an administrator.
    user_id = "USR-" + secrets.token_hex(4).upper()

    try:
        with step01.get_db() as db:
            existing = db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                return jsonify({"success": False, "error": "An account with this email already exists."}), 409

            db.execute(
                "INSERT INTO users (user_id,name,email,password_hash,role,created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    name,
                    email,
                    step01.hash_password(password),
                    role,
                    date.today().isoformat(),
                ),
            )
            db.commit()
    except Exception:
        app.logger.exception("Account registration failed")
        return jsonify({"success": False, "error": "The account could not be created. Please try again."}), 500

    if request.is_json:
        with step01.get_db() as db:
            user = dict(db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone())
        return set_auth_cookie(jsonify({"success": True, "access_token": create_access_token(user),
                                         "token_type": "Bearer", "expires_in": app.config["JWT_TTL_SECONDS"],
                                         "redirect": "/user-profile.html"}), user)
    with step01.get_db() as db:
        user = dict(db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone())
    return set_auth_cookie(redirect("/user-profile.html"), user)


@app.route("/api/user", methods=["GET"])
@app.route("/api/session", methods=["GET"])
def api_session_user():
    user = get_current_user()
    return jsonify({
        "success": True,
        "user": {
            "user_id": user["user_id"],
            "name": user["name"],
            "email": user["email"],
            "phone": user.get("phone", ""),
            "role": user["role"],
            "dashboard": role_dashboard(user["role"]),
        },
    })


@app.route("/api/user", methods=["PUT"])
def api_update_profile():
    """Update the logged-in user's name and/or password."""
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    new_name = data.get("name", "").strip()
    new_password = data.get("password", "").strip()
    phone = str(data.get("phone", user.get("phone", ""))).strip()
    if len(phone) > 40 or (phone and not re.fullmatch(r"[+()\d .-]{7,40}", phone)):
        abort(400, description="Enter a valid phone number or leave it blank.")
    if not new_name and not new_password and phone == user.get("phone", ""):
        return jsonify({"success": False, "error": "Provide a profile change to save."}), 400
    if new_password and len(new_password) < 8:
        abort(400, description="Passwords must be at least 8 characters.")
    try:
        with step01.get_db() as db:
            if new_password:
                db.execute("UPDATE users SET name=?,phone=?,password_hash=? WHERE user_id=?",
                           (new_name or user["name"], phone, step01.hash_password(new_password), user["user_id"]))
            else:
                db.execute("UPDATE users SET name=?,phone=? WHERE user_id=?",
                           (new_name or user["name"], phone, user["user_id"]))
            db.commit()
        if new_name:
            session["user_name"] = new_name
        record_application_event(user["user_id"], "user", user["user_id"], "profile_updated",
                                 {"name_changed": bool(new_name), "phone_changed": phone != user.get("phone", ""),
                                  "password_changed": bool(new_password)})
    except Exception:
        app.logger.exception("Profile update failed")
        return jsonify({"success": False, "error": "Your profile could not be updated. Please try again."}), 500
    return jsonify({"success": True, "message": "Profile updated."})


@app.route("/api/logout", methods=["GET", "POST"])
def api_logout():
    session.clear()
    token = request.cookies.get(app.config["JWT_COOKIE_NAME"], "")
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    try:
        header, payload, signature = token.split(".")
        signed = f"{header}.{payload}".encode("ascii")
        expected = hmac.new(app.secret_key.encode(), signed, hashlib.sha256).digest()
        claims = json.loads(_b64decode(payload))
        if hmac.compare_digest(expected, _b64decode(signature)) and claims.get("jti"):
            with step01.get_db() as db:
                db.execute("INSERT OR IGNORE INTO revoked_tokens(jti, expires_at) VALUES (?, ?)",
                           (claims["jti"], int(claims.get("exp", 0))))
                db.execute("DELETE FROM revoked_tokens WHERE expires_at <= ?", (int(datetime.now(timezone.utc).timestamp()),))
                db.commit()
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        pass
    response = jsonify(success=True, redirect="/login.html")
    response.delete_cookie(app.config["JWT_COOKIE_NAME"], path="/", samesite="Strict")
    return response


def record_claim_event(claim_id: str, user_id: str, event_type: str, details: Dict[str, Any]) -> None:
    with step01.get_db() as db:
        db.execute("INSERT INTO claim_events VALUES (?, ?, ?, ?, ?, ?)",
                   ("EVT-" + secrets.token_hex(6).upper(), claim_id, user_id, event_type,
                    json.dumps(details, sort_keys=True, default=str), datetime.now(timezone.utc).isoformat()))
        db.commit()


def record_application_event(user_id: str, entity_type: str, entity_id: str,
                             event_type: str, details: Dict[str, Any]) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    event_id = "EVT-" + secrets.token_hex(6).upper()
    payload = {"event_id": event_id, "timestamp": timestamp, "user_id": user_id,
               "entity_type": entity_type, "entity_id": entity_id, "action": event_type,
               "details": details, "source": "AssureX application"}
    step10.append_audit_record(payload)
    with step01.get_db() as db:
        db.execute("INSERT INTO application_audit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (event_id, user_id, entity_type, entity_id, event_type,
                    json.dumps(details, sort_keys=True, default=str), timestamp))
        db.commit()


def record_anomaly(event_type: str, severity: str, details: Dict[str, Any],
                   actor_id: str = "", entity_id: str = "") -> None:
    """Persist a security or assessment event without credentials or uploaded content."""
    with step01.get_db() as db:
        db.execute("INSERT INTO anomaly_events(event_type,severity,actor_id,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                   (event_type, severity, actor_id or None, entity_id or None,
                    json.dumps(details, sort_keys=True, default=str), datetime.now(timezone.utc).isoformat()))
        db.commit()
    response = jsonify(success=True, redirect="/login.html")
    response.delete_cookie(app.config["JWT_COOKIE_NAME"], path="/", samesite="Strict")
    return response


@app.route("/api/products", methods=["GET"])
def api_list_products():
    user = get_current_user()
    if user["role"] != "user":
        abort(403, description="Product registration is available to user accounts.")
    with step01.get_db() as db:
        products = db.execute("""SELECT p.*, w.warranty_id, w.provider AS warranty_provider,
            w.start_date AS warranty_start_date, w.expiry_date AS warranty_expiry_date,
            w.coverage AS warranty_coverage, w.exclusions AS warranty_exclusions,
            w.is_extended AS warranty_extended,w.service_center_details AS warranty_service_center
            FROM products p LEFT JOIN warranties w ON w.warranty_id=(SELECT w2.warranty_id FROM warranties w2 WHERE w2.product_id=p.product_id AND w2.user_id=p.user_id ORDER BY w2.start_date DESC,w2.created_at DESC LIMIT 1)
            WHERE p.user_id=? ORDER BY p.purchase_date DESC""", (user["user_id"],)).fetchall()
    return jsonify({
        "success": True,
        "products": [dict(p) for p in products],
    })


@app.post("/api/products")
def api_create_product():
    user = get_current_user()
    if user["role"] != "user":
        abort(403, description="Product registration is available to user accounts.")
    data = request.get_json(silent=True) or {}
    name = str(data.get("product_name", "")).strip()
    category = str(data.get("category", "")).strip()
    brand = str(data.get("brand", "")).strip()
    model = str(data.get("model", "")).strip()
    serial = str(data.get("serial_number", "")).strip()
    purchase_date = normalize_date(data.get("purchase_date"))
    retailer = str(data.get("retailer", "")).strip()
    provider = str(data.get("warranty_provider", "")).strip()
    coverage = str(data.get("coverage", "")).strip()
    exclusions = str(data.get("exclusions", "")).strip()
    service_center_details = str(data.get("service_center_details", "")).strip()
    months = parse_number(data.get("warranty_months"), "warranty duration", integer=True)
    price = parse_number(data.get("purchase_price"), "purchase price")
    if not all((name, category, brand, model, serial, purchase_date, retailer, provider, coverage)):
        abort(400, description="Complete the product and warranty details.")
    if months < 1 or months > 1200:
        abort(400, description="Warranty duration must be between 1 and 1200 months.")
    if price < 0:
        abort(400, description="Purchase price cannot be negative.")
    if date.fromisoformat(purchase_date) > date.today():
        abort(400, description="Purchase date cannot be in the future.")
    find_policy_for_category(category)
    with step01.get_db() as db:
        if db.execute("SELECT 1 FROM products WHERE user_id=? AND lower(serial_number)=lower(?)", (user["user_id"], serial)).fetchone():
            abort(409, description="A product with this serial number is already registered in your account.")
    product_id = "PRD-" + secrets.token_hex(5).upper()
    warranty_id = "WAR-" + secrets.token_hex(5).upper()
    start = date.fromisoformat(purchase_date)
    import calendar
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    expiry = date(year, month, min(start.day, calendar.monthrange(year, month)[1])).isoformat()
    created = datetime.now(timezone.utc).isoformat()
    with step01.get_db() as db:
        db.execute("INSERT INTO products (product_id,user_id,product_name,category,brand,model,serial_number,purchase_date,purchase_price,warranty_months,retailer) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (product_id, user["user_id"], name, category, brand, model, serial, purchase_date, price, months, retailer))
        db.execute("INSERT INTO warranties (warranty_id,product_id,user_id,provider,start_date,expiry_date,coverage,exclusions,is_extended,created_at,service_center_details) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (warranty_id, product_id, user["user_id"], provider, start.isoformat(), expiry,
                    coverage, exclusions, int(parse_bool(data.get("is_extended"))), created, service_center_details))
        db.commit()
    record_application_event(user["user_id"], "product", product_id, "registered",
                             {"warranty_id": warranty_id, "category": category})
    return jsonify(success=True, product={"product_id": product_id, "warranty_id": warranty_id,
        "product_name": name, "category": category, "brand": brand, "model": model,
        "serial_number": serial, "purchase_date": purchase_date, "purchase_price": price,
        "warranty_months": months, "retailer": retailer, "warranty_provider": provider,
        "warranty_start_date": start.isoformat(), "warranty_expiry_date": expiry,
        "warranty_coverage": coverage, "warranty_exclusions": exclusions,
        "warranty_service_center": service_center_details,
        "warranty_extended": parse_bool(data.get("is_extended")), "created_at": created}), 201


@app.get("/api/warranties")
def api_list_warranties():
    user = get_current_user()
    if user["role"] != "user":
        abort(403)
    with step01.get_db() as db:
        rows = db.execute("SELECT w.*, p.product_name, p.brand, p.model, p.serial_number FROM warranties w JOIN products p USING(product_id) WHERE w.user_id=? ORDER BY w.expiry_date", (user["user_id"],)).fetchall()
        lead = int(db.execute("SELECT setting_value FROM application_settings WHERE setting_key='warranty_expiry_lead_days'").fetchone()["setting_value"])
    today = date.today()
    result = []
    for row in rows:
        item = dict(row)
        remaining = (date.fromisoformat(item["expiry_date"]) - today).days
        item["days_remaining"] = remaining
        item["status"] = "Expired" if remaining < 0 else "Near expiry" if remaining <= lead else "Active"
        result.append(item)
    return jsonify(success=True, warranties=result)


@app.post("/api/products/<product_id>/warranties")
def api_add_product_warranty(product_id: str):
    user = get_current_user()
    if user["role"] != "user":
        abort(403, description="Warranty records can only be managed by product owners.")
    data = request.get_json(silent=True) or {}
    provider = str(data.get("provider", "")).strip()
    start = normalize_date(data.get("start_date")); expiry = normalize_date(data.get("expiry_date"))
    coverage = str(data.get("coverage", "")).strip(); exclusions = str(data.get("exclusions", "")).strip()
    service_details = str(data.get("service_center_details", "")).strip()
    if not provider or not start or not expiry or not coverage:
        abort(400, description="Enter a provider, valid coverage dates, and coverage terms.")
    if date.fromisoformat(start) > date.fromisoformat(expiry):
        abort(400, description="Warranty expiry must be on or after its start date.")
    with step01.get_db() as db:
        product = db.execute("SELECT product_id FROM products WHERE product_id=? AND user_id=?", (product_id, user["user_id"])).fetchone()
        if not product:
            abort(404, description="Product not found in this account.")
        warranty_id = "WAR-" + secrets.token_hex(5).upper()
        created = datetime.now(timezone.utc).isoformat()
        db.execute("INSERT INTO warranties (warranty_id,product_id,user_id,provider,start_date,expiry_date,coverage,exclusions,is_extended,created_at,service_center_details) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (warranty_id, product_id, user["user_id"], provider, start, expiry, coverage, exclusions,
                    int(parse_bool(data.get("is_extended"))), created, service_details))
        db.commit()
    record_application_event(user["user_id"], "warranty", warranty_id, "created", {"product_id": product_id, "expiry_date": expiry})
    return jsonify(success=True, warranty={"warranty_id": warranty_id, "product_id": product_id, "provider": provider,
                                            "start_date": start, "expiry_date": expiry, "is_extended": parse_bool(data.get("is_extended"))}), 201


@app.get("/api/products/<product_id>/repairs")
def api_list_repairs(product_id: str):
    user = get_current_user()
    if user["role"] != "user":
        abort(403)
    with step01.get_db() as db:
        if not db.execute("SELECT 1 FROM products WHERE product_id=? AND user_id=?", (product_id, user["user_id"])).fetchone():
            abort(404, description="Product not found.")
        rows = db.execute("SELECT repair_id,product_id,repair_date,service_center,parts_replaced,outcome,cost,authorized,created_at FROM repairs WHERE product_id=? AND user_id=? ORDER BY repair_date DESC", (product_id, user["user_id"])).fetchall()
    return jsonify(success=True, repairs=[dict(row) for row in rows])


@app.post("/api/products/<product_id>/repairs")
def api_create_repair(product_id: str):
    user = get_current_user()
    if user["role"] != "user":
        abort(403)
    data = request.get_json(silent=True) or {}
    repair_date = normalize_date(data.get("repair_date"))
    center = str(data.get("service_center", "")).strip()
    outcome = str(data.get("outcome", "")).strip()
    parts = str(data.get("parts_replaced", "")).strip()
    cost = parse_number(data.get("cost") or 0, "repair cost")
    if not repair_date or not center or not outcome:
        abort(400, description="Enter the repair date, service center and outcome.")
    repair_id = "RPR-" + secrets.token_hex(5).upper()
    created = datetime.now(timezone.utc).isoformat()
    with step01.get_db() as db:
        product = db.execute("SELECT 1 FROM products WHERE product_id=? AND user_id=?", (product_id, user["user_id"])).fetchone()
        if not product:
            abort(404, description="Product not found.")
        db.execute("INSERT INTO repairs VALUES (?,?,?,?,?,?,?,?,?,?,?)", (repair_id, product_id, user["user_id"], repair_date, center, parts, outcome, cost, int(parse_bool(data.get("authorized"))), None, created))
        db.commit()
    record_application_event(user["user_id"], "repair", repair_id, "recorded", {"product_id": product_id, "authorized": bool(data.get("authorized"))})
    return jsonify(success=True, repair={"repair_id": repair_id, "product_id": product_id,
        "repair_date": repair_date, "service_center": center, "parts_replaced": parts,
        "outcome": outcome, "cost": cost, "authorized": parse_bool(data.get("authorized")),
        "created_at": created}), 201


# -----------------------------------------------------------------------------
# Claim Processing: Upload & Extract (Steps 2, 3, 4)
# -----------------------------------------------------------------------------
@app.route("/api/claim/process", methods=["POST"])
@app.route("/api/process-extraction", methods=["POST"])
@serialized
def api_process_extraction():
    """
    Step 2: Collect claim details and uploaded files.
    Step 3: SHA-256 fingerprinting and duplicate detection.
    Step 4: Receipt OCR text & field extraction.
    """
    user = get_current_user()
    service_intake = user["role"] == "service_center"
    if user["role"] not in {"user", "service_center"}:
        abort(403, description="Only customers and service centers can submit claim intake.")
    if not request.files.get("receipt") and not request.files.get("purchase_receipt"):
        abort(400, description="Upload a purchase receipt to begin.")
    claim_id = "CLM-" + secrets.token_hex(8).upper()
    claim_dir = CLAIMS_DIR / claim_id
    claim_dir.mkdir(parents=True, exist_ok=True)

    owner_id = user["user_id"]
    if service_intake:
        owner_id = request.form.get("customer_user_id", "").strip()
        if not owner_id:
            abort(400, description="Select the customer account for this intake.")
        with step01.get_db() as db:
            customer = db.execute("SELECT user_id FROM users WHERE user_id=? AND role='user'", (owner_id,)).fetchone()
        if not customer:
            abort(404, description="Customer account not found.")
    selected_product_id = request.form.get("product_id", "").strip()
    registered_product = None
    if selected_product_id:
        with step01.get_db() as db:
            product_row = db.execute("SELECT * FROM products WHERE product_id=? AND user_id=?",
                                     (selected_product_id, owner_id)).fetchone()
        if not product_row:
            abort(404, description="Registered product not found for this account.")
        registered_product = dict(product_row)
    category = (registered_product or {}).get("category") or request.form.get("category", "").strip()
    find_policy_for_category(category)
    repair_count = parse_number(request.form.get("previous_repair_count") or 0, "previous repair count", integer=True)
    claim_title = request.form.get("claim_title") or request.form.get("title") or request.form.get("fault_category") or ""
    if len(claim_title.strip()) < 3 or len(claim_title) > 160:
        abort(400, description="Enter a fault category between 3 and 160 characters.")
    fault_date = normalize_date(request.form.get("fault_date"))
    if not fault_date or date.fromisoformat(fault_date) > date.today():
        abort(400, description="Enter a valid fault date that is not in the future.")
    purchase_date_input = request.form.get("purchase_date") or None
    issue_description = request.form.get("issue_description") or request.form.get("description", "")
    if len(issue_description.strip()) < 10 or len(issue_description) > 3000:
        abort(400, description="Describe the fault in 10 to 3,000 characters.")

    # Document uploads
    documents_info = {}
    fingerprints = []
    duplicate_flags = []
    registry = step03.load_registry()

    doc_keys = [
        ("purchase_receipt", request.files.get("receipt") or request.files.get("purchase_receipt")),
        ("warranty_card", request.files.get("warranty") or request.files.get("warranty_card")),
        ("fault_evidence", request.files.get("damage") or request.files.get("fault_evidence") or request.files.get("damage_photo")),
        ("product_image", request.files.get("product_image")),
        ("serial_number_evidence", request.files.get("serial_number_evidence")),
        ("repair_report", request.files.get("repair_report")),
        ("fault_video", request.files.get("fault_video")),
    ]

    for doc_type, file_obj in doc_keys:
        if file_obj and file_obj.filename:
            safe_filename = secure_filename(file_obj.filename)
            if Path(safe_filename).suffix.lower() not in {".png", ".jpg", ".jpeg", ".pdf", ".webp", ".bmp", ".tiff", ".mp4", ".mov", ".webm"}:
                record_anomaly("unsupported_upload_type", "medium", {"document_type": doc_type, "extension": Path(safe_filename).suffix.lower()}, user["user_id"], claim_id)
                abort(400, description="Use an image, PDF, or supported video document.")
            dest_path = claim_dir / f"{doc_type}_{safe_filename}"
            file_obj.save(str(dest_path))

            # Step 3 SHA-256 Fingerprint
            digest = step03.sha256_file(dest_path)
            old_record = registry.get(digest)
            is_duplicate = old_record is not None and old_record.get("claim_id") != claim_id

            if is_duplicate:
                duplicate_flags.append(
                    f"Duplicate document: {doc_type} matches Claim {old_record['claim_id']} ({old_record['filename']})"
                )
            elif old_record is None:
                registry[digest] = {
                    "claim_id": claim_id,
                    "document_type": doc_type,
                    "filename": safe_filename,
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }

            doc_record = {
                "document_type": doc_type,
                "filename": safe_filename,
                "path": str(dest_path),
                "sha256": digest,
                "duplicate": is_duplicate,
                "size_bytes": dest_path.stat().st_size,
            }
            documents_info[doc_type] = doc_record
            fingerprints.append(doc_record)
    step03.save_registry(registry)

    # Step 4: Multi-Engine OCR (PaddleOCR -> EasyOCR -> Tesseract fallback)
    extracted_fields = {key: None for key in ("invoice_number", "store_name", "serial_number", "purchase_date", "paid_amount", "warranty_months", "product_name", "model_number")}
    ocr_results = {}
    warranty_ocr_fields: dict = {}

    # --- Receipt OCR ---
    receipt_file = documents_info.get("purchase_receipt")
    if receipt_file and Path(receipt_file["path"]).exists():
        try:
            ocr_result = step04.ocr_document(receipt_file["path"], mode="receipt", engine=os.environ.get("ASSUREX_OCR_ENGINE", "auto"))
            ocr_results["purchase_receipt"] = ocr_result
            parsed = dict(ocr_result.get("extracted_fields", {}))
            parsed["paid_amount"] = parsed.pop("amount_paid", None)
            parsed["purchase_date"] = normalize_date(parsed.get("purchase_date"))
            extracted_fields["_ocr_engine"] = ocr_result.get("engine_used", "unknown")
            for k, v in parsed.items():
                if v is not None:
                    extracted_fields[k] = v
        except Exception as _ocr_err:
            app.logger.exception("Receipt OCR failed")
            ocr_results["purchase_receipt"] = {"ocr_status": "unavailable", "raw_text": "", "error": "Text could not be read. Upload a clearer receipt or enter the details for manual review."}
            extracted_fields["_ocr_engine"] = "unavailable"

    # --- Warranty Card OCR ---
    warranty_file = documents_info.get("warranty_card")
    if warranty_file and Path(warranty_file["path"]).exists():
        try:
            w_result = step04.ocr_document(warranty_file["path"], mode="warranty", engine=os.environ.get("ASSUREX_OCR_ENGINE", "auto"))
            ocr_results["warranty_card"] = w_result
            warranty_ocr_fields = w_result.get("extracted_fields", {})
            warranty_ocr_fields["_ocr_engine"] = w_result.get("engine_used", "unknown")
            r_serial = str(extracted_fields.get("serial_number", "")).strip().lower()
            w_serial = str(warranty_ocr_fields.get("serial_number", "")).strip().lower()
            if r_serial and w_serial and r_serial != w_serial:
                extracted_fields["_serial_mismatch_warning"] = (
                    f"Receipt SN ({r_serial}) differs from Warranty Card SN ({w_serial})"
                )
            if not extracted_fields.get("warranty_months") and warranty_ocr_fields.get("warranty_months"):
                extracted_fields["warranty_months"] = warranty_ocr_fields["warranty_months"]
        except Exception as _wocr_err:
            app.logger.exception("Warranty OCR failed")
            ocr_results["warranty_card"] = {"ocr_status": "unavailable", "raw_text": "", "error": "Warranty text could not be read."}

    # Read serial labels from independent evidence sources when OCR supports them.
    serial_evidence = {}
    for doc_type in ("serial_number_evidence", "repair_report"):
        source = documents_info.get(doc_type)
        if source and Path(source["path"]).suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf", ".webp", ".bmp", ".tiff"}:
            try:
                parsed = step04.ocr_document(source["path"], mode="receipt", engine=os.environ.get("ASSUREX_OCR_ENGINE", "auto"))
                serial_value = (parsed.get("extracted_fields") or {}).get("serial_number")
                if serial_value:
                    serial_evidence[doc_type] = str(serial_value).strip()
            except Exception:
                app.logger.exception("Serial evidence OCR failed for %s", doc_type)
    serial_values = {"registered/product": (registered_product or {}).get("serial_number") or request.form.get("serial_number", ""),
                     "receipt": extracted_fields.get("serial_number"), "warranty": warranty_ocr_fields.get("serial_number"), **serial_evidence}
    serial_values = {key: str(value).strip().casefold() for key, value in serial_values.items() if value and str(value).strip()}
    serial_mismatches = [f"{left} serial differs from {right} serial" for i, (left, a) in enumerate(serial_values.items()) for right, b in list(serial_values.items())[i+1:] if a != b]

    # Build and cache step data
    claim_payload = {
        "claim_id": claim_id,
        "user_id": owner_id,
        "intake_actor_id": user["user_id"],
        "intake_actor_role": user["role"],
        "category": category,
        "product": {
            "product_id": (registered_product or {}).get("product_id") or "PRD-" + secrets.token_hex(5).upper(),
            "product_name": (registered_product or {}).get("product_name") or " ".join(filter(None, [request.form.get("brand"), request.form.get("model")])) or category,
            "category": category,
            "brand": (registered_product or {}).get("brand") or request.form.get("brand", ""),
            "model": (registered_product or {}).get("model") or request.form.get("model", ""),
            "serial_number": (registered_product or {}).get("serial_number") or request.form.get("serial_number", ""),
            "purchase_date": extracted_fields["purchase_date"],
            "purchase_price": None,
            "warranty_months": extracted_fields.get("warranty_months"),
            "retailer": extracted_fields["store_name"],
        },
        "fault_date": fault_date,
        "fault_description": issue_description,
        "fault_category": request.form.get("fault_category", claim_title),
        "damage_type": request.form.get("damage_type", ""),
        "previous_repair_count": repair_count,
        "previous_repair": repair_count > 0,
        "previous_replacement": request.form.get("previous_replacement") == "yes",
        "replacement_date": normalize_date(request.form.get("replacement_date")),
        "replacement_details": request.form.get("replacement_details", "").strip(),
        "repair_center": request.form.get("repair_center", ""),
        "replaced_parts": request.form.get("replaced_parts", ""),
        "unauthorized_repair": request.form.get("unauthorized_repair") == "yes",
        "ocr": ocr_results,
        "warranty_ocr_fields": warranty_ocr_fields,
        "claim_submission_date": date.today().isoformat(),
        "documents": documents_info,
        "serial_evidence_ocr": serial_evidence,
        "serial_mismatches": serial_mismatches,
        "document_fingerprints": fingerprints,
        "duplicate_flags": duplicate_flags,
        "preparation": {
            "missing_documents": [key.replace("_", " ").title() for key in find_policy_for_category(category).get("mandatory_documents", ["purchase_receipt", "warranty_card", "fault_evidence"]) if key not in documents_info],
            "serial_warnings": serial_mismatches,
            "actions": (["Add a clear warranty card if available."] if "warranty_card" not in documents_info else []) + (["Add a photo or video showing the fault."] if "fault_evidence" not in documents_info else []) + (["Check the serial number against each uploaded source."] if serial_mismatches else []),
        },
        "document_duplicate_found": bool(duplicate_flags),
        "extracted_fields": extracted_fields,
        "status": "Extracted",
    }

    (OUTPUTS_DIR / "step02_claim.json").write_text(json.dumps(claim_payload, indent=2), encoding="utf-8")
    (OUTPUTS_DIR / "step03_fingerprints.json").write_text(
        json.dumps({
            "claim_id": claim_id,
            "fingerprints": fingerprints,
            "duplicate_flags": duplicate_flags,
        }, indent=2),
        encoding="utf-8",
    )
    (claim_dir / "claim_draft.json").write_text(json.dumps(claim_payload, indent=2), encoding="utf-8")
    created_at = datetime.now(timezone.utc).isoformat()
    with step01.get_db() as db:
        db.execute("INSERT INTO claims (claim_id,user_id,product_id,category,claim_title,serial_number,fault_description,status,status_stage,created_at,updated_at,intake_actor_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (claim_id, owner_id, claim_payload["product"]["product_id"], category,
                    claim_title, claim_payload["product"].get("serial_number"), issue_description,
                    "Submitted", "Submitted", created_at, created_at, user["user_id"] if service_intake else None))
        db.commit()
    push_notification(owner_id, claim_id, f"Claim {claim_id} has been submitted for assessment.")
    if claim_payload["preparation"]["missing_documents"]:
        push_notification(owner_id, claim_id, f"Claim {claim_id} needs documents: {', '.join(claim_payload['preparation']['missing_documents'])}.")
    record_claim_event(claim_id, owner_id, "evidence_uploaded", {
        "product_id": claim_payload["product"]["product_id"],
        "document_types": sorted(documents_info), "fingerprint_count": len(fingerprints),
        "fingerprints": [{"document_type": item["document_type"], "sha256": item["sha256"]} for item in fingerprints],
    })
    if service_intake:
        record_application_event(user["user_id"], "claim", claim_id, "service_center_intake_created",
                                 {"customer_user_id": owner_id, "product_id": claim_payload["product"]["product_id"]})
    if duplicate_flags:
        record_anomaly("duplicate_documents", "high", {"document_count": len(duplicate_flags)}, user["user_id"], claim_id)
    if serial_mismatches:
        record_anomaly("serial_number_mismatch", "high", {"source_conflict_count": len(serial_mismatches)}, user["user_id"], claim_id)

    return jsonify({
        "success": True,
        "claim_id": claim_id,
        "fingerprints": fingerprints,
        "extracted_fields": extracted_fields,
        "warranty_ocr_fields": warranty_ocr_fields,
        "ocr": ocr_results,
        "duplicate_flags": duplicate_flags,
        "preparation": claim_payload["preparation"],
    })


# -----------------------------------------------------------------------------
# Claim Evaluation: Decision, Rule Engine, AI Arbiter & PDF (Steps 5-10)
# -----------------------------------------------------------------------------
@app.route("/api/claim/evaluate", methods=["POST"])
@serialized
def api_evaluate_claim():
    """
    Step 5: Verified receipt data.
    Step 6: Corrected Python ML model + 800x600 Claim Summary Card.
    Step 7: Arbiter model comparison.
    Step 8: Warranty rule engine evaluation.
    Step 9: Final Master Decision.
    Step 10: Hash-chained audit logging + ReportLab PDF audit certificate.
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    claim_id = data.get("claim_id", "")
    if not re.fullmatch(r"CLM-[A-F0-9]{16}", claim_id):
        abort(404, description="Upload documents before requesting an assessment.")
    draft_file = CLAIMS_DIR / claim_id / "claim_draft.json"
    if not draft_file.exists():
        abort(404, description="Claim draft not found.")
    claim = json.loads(draft_file.read_text(encoding="utf-8"))
    current_user = get_current_user()
    if current_user["role"] not in {"user", "service_center"}:
        abort(403, description="Only customers and service-center intake staff can assess a claim.")
    is_owner = current_user["role"] == "user" and claim["user_id"] == current_user["user_id"]
    is_intake_actor = current_user["role"] == "service_center" and claim.get("intake_actor_id") == current_user["user_id"]
    if not (is_owner or is_intake_actor):
        abort(403)
    if data.get("confirmed") is not True:
        abort(400, description="Confirm the extracted details before assessment.")
    result_file = CLAIMS_DIR / claim_id / "result.json"
    if result_file.exists():
        return jsonify(json.loads(result_file.read_text(encoding="utf-8")))

    # Step 5: Save verified receipt data
    verified_data = {key: str(data.get(key) or "").strip() for key in ("invoice_number", "store_name", "serial_number", "purchase_date")}
    verified_data["purchase_date"] = normalize_date(verified_data["purchase_date"])
    if not verified_data["purchase_date"]:
        abort(400, description="Enter a valid purchase date.")
    verified_data["retailer"] = verified_data["store_name"]
    verified_data["amount_paid"] = parse_number(data.get("paid_amount"), "purchase price")
    verified_data["warranty_months"] = parse_number(data.get("warranty_months"), "warranty duration", integer=True)
    verified_data["product_name"] = str(data.get("product_name") or claim["product"].get("product_name") or "").strip()[:160]
    verified_data["model_number"] = str(data.get("model_number") or claim["product"].get("model") or "").strip()[:120]
    if verified_data["warranty_months"] > 1200:
        abort(400, description="Warranty duration must be 1200 months or less.")
    claim["product"].update(purchase_date=verified_data["purchase_date"], purchase_price=verified_data["amount_paid"], warranty_months=verified_data["warranty_months"], product_name=verified_data["product_name"], model=verified_data["model_number"])
    claim["verified_receipt_data"] = verified_data
    claim["verification_status"] = "human_confirmed"
    record_claim_event(claim_id, claim["user_id"], "details_verified", {
        "field_names": sorted(verified_data), "verification_status": "human_confirmed"})
    record_application_event(claim["user_id"], "claim", claim_id, "details_verified",
                             {"field_names": sorted(verified_data)})
    with step01.get_db() as db:
        claim["repair_records"] = [dict(row) for row in db.execute(
            "SELECT repair_date,service_center,parts_replaced,outcome,cost,authorized FROM repairs WHERE product_id=? AND user_id=? ORDER BY repair_date",
            (claim["product"]["product_id"], claim["user_id"])) .fetchall()]
        warranty_row = db.execute("SELECT * FROM warranties WHERE product_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1",
                                  (claim["product"]["product_id"], claim["user_id"])).fetchone()
    if warranty_row:
        claim["product"]["warranty_expiry_date"] = warranty_row["expiry_date"]
        claim["product"]["is_extended"] = bool(warranty_row["is_extended"])
        claim["product"]["warranty_provider"] = warranty_row["provider"]
    (OUTPUTS_DIR / "step05_verified_claim.json").write_text(json.dumps(claim, indent=2, default=str), encoding="utf-8")

    # Advance status to 'Under Evaluation'
    advance_claim_status(claim_id, "Under Evaluation", claim.get("user_id", ""))

    # --- Duplicate Claim Detection (by invoice_number OR serial_number) ---
    duplicate_claim_flags: List[str] = []
    inv_num = verified_data.get("invoice_number", "")
    ser_num = verified_data.get("serial_number", "")
    try:
        with step01.get_db() as db:
            if inv_num:
                dups = db.execute(
                    "SELECT claim_id FROM claims WHERE invoice_number = ? AND claim_id != ?",
                    (inv_num, claim_id),
                ).fetchall()
                for d in dups:
                    duplicate_claim_flags.append(f"Duplicate invoice #{inv_num} found in claim {d['claim_id']}")
            if ser_num:
                dups_sn = db.execute(
                    "SELECT claim_id, status FROM claims WHERE serial_number = ? AND claim_id != ?",
                    (ser_num, claim_id),
                ).fetchall()
                for d in dups_sn:
                    if d["status"] not in ("Rejected", "Closed"):
                        duplicate_claim_flags.append(f"Active claim for SN {ser_num} already exists: {d['claim_id']}")
            normalized_fault = re.sub(r"[^a-z0-9 ]", " ", claim.get("fault_description", "").lower())
            normalized_fault = " ".join(normalized_fault.split())
            if len(normalized_fault) >= 30:
                candidates = db.execute("SELECT claim_id,fault_description FROM claims WHERE user_id=? AND category=? AND claim_id<>? AND status_stage NOT IN ('Rejected','Closed') ORDER BY created_at DESC LIMIT 100",
                                        (claim["user_id"], claim.get("category", ""), claim_id)).fetchall()
                for candidate in candidates:
                    prior_text = " ".join(re.sub(r"[^a-z0-9 ]", " ", (candidate["fault_description"] or "").lower()).split())
                    if len(prior_text) >= 30 and SequenceMatcher(None, normalized_fault, prior_text).ratio() >= 0.90:
                        duplicate_claim_flags.append(f"Fault description closely matches claim {candidate['claim_id']}; review for a duplicate submission.")
                        break
    except step01.DatabaseError:
        app.logger.exception("Duplicate claim screening failed for %s", claim_id)
        duplicate_claim_flags.append("Duplicate claim screening could not be completed; reviewer confirmation is required.")

    # --- Contradiction Detection ---
    contradiction_flags: List[str] = []
    try:
        from datetime import datetime as _dt
        p_date_str = verified_data.get("purchase_date", "")
        fault_date_str = claim.get("fault_date", date.today().isoformat())
        claim_submission = claim.get("claim_submission_date", date.today().isoformat())
        if p_date_str:
            p_date = _dt.strptime(p_date_str[:10], "%Y-%m-%d").date()
            today = date.today()
            if p_date > today:
                contradiction_flags.append(f"Purchase date {p_date_str} is in the future")
            if fault_date_str:
                f_date = _dt.strptime(fault_date_str[:10], "%Y-%m-%d").date()
                if f_date < p_date:
                    contradiction_flags.append(f"Fault date {fault_date_str} is before purchase date {p_date_str}")
            if claim_submission:
                c_date = _dt.strptime(claim_submission[:10], "%Y-%m-%d").date()
                if c_date < p_date:
                    contradiction_flags.append(f"Claim submission date {claim_submission} is before purchase date")
        contradiction_flags.extend(claim.get("serial_mismatches", []))
        if claim.get("extracted_fields", {}).get("_serial_mismatch_warning"):
            contradiction_flags.append(claim["extracted_fields"]["_serial_mismatch_warning"])
        extracted_model = claim.get("extracted_fields", {}).get("model_number")
        verified_model = verified_data.get("model_number")
        if extracted_model and verified_model and re.sub(r"\s+", "", extracted_model).casefold() != re.sub(r"\s+", "", verified_model).casefold():
            contradiction_flags.append("The model number entered for verification differs from receipt OCR.")
        replacement_date = claim.get("replacement_date")
        if replacement_date:
            replaced_on = _dt.strptime(replacement_date[:10], "%Y-%m-%d").date()
            if replaced_on > date.today() or (p_date_str and replaced_on < _dt.strptime(p_date_str[:10], "%Y-%m-%d").date()):
                contradiction_flags.append("The recorded replacement date conflicts with the product purchase date or current date.")
    except (ValueError, TypeError):
        app.logger.exception("Claim chronology could not be validated: %s", claim_id)
        abort(400, description="One or more dates are invalid. Check the dates and submit again.")

    if duplicate_claim_flags:
        claim.setdefault("duplicate_claim_flags", []).extend(duplicate_claim_flags)
    if contradiction_flags:
        claim.setdefault("contradiction_flags", []).extend(contradiction_flags)

    # Step 8: Warranty Rule Engine Evaluation
    category = claim.get("product", {}).get("category", "Smartphone")
    policy = find_policy_for_category(category)
    warranty_result = step08.evaluate_rules(claim, policy)
    (OUTPUTS_DIR / "step08_warranty_result.json").write_text(json.dumps(warranty_result, indent=2, default=str), encoding="utf-8")


    # Inference never falls back to a manufactured prediction or confidence.
    python_prediction = {}
    model_error = None
    try:
        python_prediction = step06.run_python_model(MODELS_DIR / "best_corrected_assurex_model.joblib", MODELS_DIR / "corrected_label_encoder.joblib", claim)
    except Exception:
        app.logger.exception("Model inference failed")
        model_error = "The claim model is unavailable. No prediction has been substituted."
        record_anomaly("tabular_model_failure", "high", {"model": "corrected_claim_model", "error_type": type(__import__('sys').exc_info()[1]).__name__}, current_user["user_id"], claim_id)
    tm_prediction = {}
    comparison = {}
    comparison_error = None
    try:
        card_path = CLAIMS_DIR / claim_id / "summary.png"
        step06.generate_summary_card(claim, card_path)
        tm_adapter = importlib.import_module("06b_teachable_machine_inference")
        tm_prediction = tm_adapter.predict(MODELS_DIR / "claim_card_hog.joblib", MODELS_DIR / "claim_card_labels.txt", card_path)
        if python_prediction:
            comparison = step07.compare_one({"python": python_prediction}, tm_prediction,
                                             step07.load_thresholds(POLICIES_DIR / "model_comparison.json"))
    except Exception:
        app.logger.exception("Independent image comparison failed")
        comparison_error = "Independent image comparison is unavailable. A manual reviewer will assess this claim."
        record_anomaly("image_model_failure", "high", {"model": "claim_card_image_model", "error_type": type(__import__('sys').exc_info()[1]).__name__}, current_user["user_id"], claim_id)

    # Step 9: Final Master Decision
    hard_failures = warranty_result.get("hard_failures", [])
    manual_reasons = list(warranty_result.get("manual_review_flags", []))
    decision_config = step07.load_thresholds(POLICIES_DIR / "model_comparison.json")
    if model_error:
        manual_reasons.append(model_error)
    for document in ("purchase_receipt", "warranty_card"):
        if claim.get("ocr", {}).get(document, {}).get("ocr_status") != "completed":
            manual_reasons.append(f"{document.replace('_', ' ')} could not be verified by OCR.")
    if not claim["product"].get("serial_number") or not verified_data.get("serial_number"):
        manual_reasons.append("Product or receipt serial number is missing.")
    if python_prediction and python_prediction["confidence"] < decision_config["python_manual_review_below"]:
        manual_reasons.append(f"Model confidence is below the configured {decision_config['python_manual_review_below']:.0%} review threshold.")
        record_anomaly("low_model_confidence", "medium", {"model": "corrected_claim_model", "confidence": python_prediction["confidence"]}, current_user["user_id"], claim_id)
    if not tm_prediction or not comparison:
        manual_reasons.append("Independent image model is unavailable; reviewer assessment is required.")
    if python_prediction.get("prediction") == "Manual Review":
        manual_reasons.append("The claim model recommends manual review.")
    if claim.get("document_duplicate_found"):
        manual_reasons.append("Duplicate document flag detected")
    if duplicate_claim_flags:
        manual_reasons.extend(duplicate_claim_flags)
        record_anomaly("duplicate_claim_signal", "high", {"signal_count": len(duplicate_claim_flags)}, current_user["user_id"], claim_id)
    if contradiction_flags:
        manual_reasons.extend(contradiction_flags)
    if comparison.get("manual_review_trigger"):
        manual_reasons.append(comparison.get("consistency_status", "Model discrepancy"))
        record_anomaly("model_disagreement", "medium", {"status": comparison.get("consistency_status"), "python_prediction": python_prediction.get("prediction"), "image_prediction": tm_prediction.get("prediction")}, current_user["user_id"], claim_id)

    if manual_reasons:
        final_decision = "Manual Review Required"
        status_type = "review"
    elif hard_failures or python_prediction.get("prediction") == "Invalid Claim":
        final_decision = "Likely Invalid"
        status_type = "invalid"
    elif python_prediction.get("prediction") == "Valid Claim" and warranty_result.get("rule_status") == "PASS":
        final_decision = "Likely Valid"
        status_type = "valid"
    else:
        final_decision = "Manual Review Required"
        status_type = "review"
    risk_level = "high" if hard_failures or status_type == "invalid" else "medium" if manual_reasons else "low"

    explanation_parts = [
        f"Claim model: {python_prediction.get('prediction', 'Unavailable')}",
        f"Independent comparison: {tm_prediction.get('prediction', 'Unavailable')}",
        f"Model comparison: {comparison.get('consistency_status', 'Unavailable')}",
        f"Warranty Policy: {warranty_result.get('rule_status')}",
    ]
    if hard_failures:
        explanation_parts.append("Hard Failures: " + "; ".join(hard_failures))
    if manual_reasons:
        explanation_parts.append("Review Reasons: " + "; ".join(manual_reasons))

    decision_payload = {
        "claim_id": claim_id,
        "decision": final_decision,
        "explanation": " | ".join(explanation_parts),
        "manual_review_required": final_decision == "Manual Review Required",
        "ai_results": {
            "python": python_prediction,
            "image_model": tm_prediction,
            "comparison": comparison,
        },
        "warranty": warranty_result,
    }
    (OUTPUTS_DIR / "step09_final_decision.json").write_text(json.dumps(decision_payload, indent=2, default=str), encoding="utf-8")

    # Persist the product/warranty entities as soon as the owner confirms the receipt.
    product = claim["product"]
    with step01.get_db() as db:
        existing_product = db.execute("SELECT 1 FROM products WHERE product_id=? AND user_id=?",
                                      (product["product_id"], claim["user_id"])).fetchone()
        if not existing_product:
            db.execute("INSERT INTO products (product_id,user_id,product_name,category,brand,model,serial_number,purchase_date,purchase_price,warranty_months,retailer) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (product["product_id"], claim["user_id"], product.get("product_name") or category,
                        category, product.get("brand", ""), product.get("model", ""), product.get("serial_number", ""),
                        verified_data["purchase_date"], verified_data["amount_paid"], verified_data["warranty_months"],
                        verified_data.get("store_name") or "Not recorded"))
        existing_warranty = db.execute("SELECT 1 FROM warranties WHERE product_id=? AND user_id=?",
                                       (product["product_id"], claim["user_id"])).fetchone()
        if not existing_warranty:
            purchase = date.fromisoformat(verified_data["purchase_date"])
            import calendar
            month_index = purchase.month - 1 + verified_data["warranty_months"]
            end_year = purchase.year + month_index // 12
            end_month = month_index % 12 + 1
            end_date = date(end_year, end_month, min(purchase.day, calendar.monthrange(end_year, end_month)[1]))
            db.execute("INSERT INTO warranties (warranty_id,product_id,user_id,provider,start_date,expiry_date,coverage,exclusions,is_extended,created_at,service_center_details) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       ("WAR-" + secrets.token_hex(5).upper(), product["product_id"], claim["user_id"],
                        str(policy.get("provider") or "Provider not recorded"), purchase.isoformat(), end_date.isoformat(),
                        json.dumps(policy.get("covered_fault_categories", [])),
                        json.dumps(policy.get("excluded_damage", [])), 0, datetime.now(timezone.utc).isoformat(), ""))
        db.commit()

    # Step 10: Audit Log & Certificate Generation
    reviewer_info = {
        "reviewer": "AssureX assessment",
        "action": "Auto-Evaluated",
        "reason": "Evaluated against 10-step AssureX engine.",
    }
    audit_record = step10.append_audit_record({
        "event_id": "AUD-" + secrets.token_hex(6).upper(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "claim_id": claim_id,
        "automated_decision": final_decision,
        "python_prediction": python_prediction.get("prediction"),
        "python_confidences": python_prediction.get("confidences"),
        "tm_prediction": tm_prediction.get("prediction"),
        "tm_confidences": tm_prediction.get("confidences"),
        "consistency_status": comparison.get("consistency_status"),
        "confidence_difference": comparison.get("confidence_difference"),
        "warranty_rule_status": warranty_result.get("rule_status"),
        "warranty_hard_failures": hard_failures,
        "warranty_manual_flags": manual_reasons,
        "reviewer": reviewer_info["reviewer"],
        "action": reviewer_info["action"],
        "reason": reviewer_info["reason"],
        "source": "ClaimSure_AI",
    })
    reviewer_info["record_hash"] = audit_record["record_hash"]

    # Build PDF Audit Certificate
    pdf_filename = f"assurex_audit_{claim_id}.pdf"
    pdf_path = OUTPUTS_DIR / pdf_filename
    try:
        step10.build_pdf(pdf_path, decision_payload, claim, reviewer_info)
    except Exception:
        app.logger.exception("PDF generation failed")

    # Save to SQLite Database
    try:
        with step01.get_db() as db:
            db.execute(
                """
                INSERT INTO claims (claim_id,user_id,product_id,category,claim_title,purchase_date,fault_description,invoice_number,store_name,serial_number,paid_amount,status,status_stage,decision,automated_decision,confidence,explanation,certificate_path,model_version,duplicate_flag,model_consistency,risk_level,created_at,updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(claim_id) DO UPDATE SET product_id=excluded.product_id,category=excluded.category,
                claim_title=excluded.claim_title,purchase_date=excluded.purchase_date,fault_description=excluded.fault_description,
                invoice_number=excluded.invoice_number,store_name=excluded.store_name,serial_number=excluded.serial_number,
                paid_amount=excluded.paid_amount,status=excluded.status,
                decision=excluded.decision,automated_decision=excluded.automated_decision,confidence=excluded.confidence,explanation=excluded.explanation,
                certificate_path=excluded.certificate_path,model_version=excluded.model_version,
                duplicate_flag=excluded.duplicate_flag,model_consistency=excluded.model_consistency,risk_level=excluded.risk_level,updated_at=excluded.updated_at
                """,
                (
                    claim_id,
                    claim["user_id"],
                    product["product_id"],
                    category,
                    claim["product"].get("product_name") or category,
                    verified_data.get("purchase_date"),
                    claim.get("fault_description", ""),
                    verified_data.get("invoice_number"),
                    verified_data.get("store_name"),
                    verified_data.get("serial_number"),
                    verified_data.get("amount_paid"),
                    "Approved" if status_type == "valid" else ("Rejected" if status_type == "invalid" else "Pending Review"),
                    "Approved" if status_type == "valid" else ("Rejected" if status_type == "invalid" else "Manual Review"),
                    final_decision,
                    final_decision,
                    python_prediction.get("confidence"),
                    " | ".join(explanation_parts),
                    pdf_filename if pdf_path.exists() else None,
                    python_prediction.get("model_version"),
                    int(bool(claim.get("document_duplicate_found") or duplicate_claim_flags)),
                    comparison.get("consistency_status"),
                    risk_level,
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            db.commit()
    except Exception:
        app.logger.exception("Claim could not be saved")
        abort(500)

    advance_claim_status(claim_id, "Manual Review" if status_type == "review" else "Approved" if status_type == "valid" else "Rejected", claim["user_id"])
    record_claim_event(claim_id, claim["user_id"], "assessment_completed", {
        "decision": final_decision, "model_version": python_prediction.get("model_version"),
        "python_prediction": python_prediction.get("prediction"), "image_prediction": tm_prediction.get("prediction"),
    })
    record_application_event(claim["user_id"], "claim", claim_id, "assessment_completed", {
        "decision": final_decision, "model_version": python_prediction.get("model_version")})
    with step01.get_db() as db:
        db.execute("UPDATE claims SET image_model_version=? WHERE claim_id=?", ((tm_prediction or {}).get("model_version"), claim_id))
        db.execute("INSERT OR REPLACE INTO prediction_records (claim_id,python_result,image_result,comparison,rule_results,final_decision,model_version,created_at,image_model_version) VALUES (?,?,?,?,?,?,?,?,?)",
                   (claim_id, json.dumps(python_prediction or {}, default=str), json.dumps(tm_prediction or {}, default=str),
                    json.dumps(comparison or {}, default=str), json.dumps(warranty_result, default=str), final_decision,
                    python_prediction.get("model_version"), datetime.now(timezone.utc).isoformat(),
                    (tm_prediction or {}).get("model_version")))
        db.commit()

    supporting_factors = list(warranty_result.get("passed_rules", []))
    opposing_factors = list(warranty_result.get("hard_failures", [])) + list(warranty_result.get("warnings", []))
    if claim.get("serial_mismatches"):
        opposing_factors.extend(claim["serial_mismatches"])
    if claim.get("document_duplicate_found"):
        opposing_factors.append("One or more uploaded documents match another claim.")
    if comparison.get("consistency_status"):
        (supporting_factors if comparison.get("consistency_status") in {"Strong", "Acceptable"} else opposing_factors).append(
            f"Independent image and tabular models: {comparison['consistency_status']}.")
    if not supporting_factors:
        supporting_factors.append("No supporting policy rule was recorded.")
    if not opposing_factors:
        opposing_factors.append("No policy warning or contradiction was recorded.")
    claim_summary = (f"{category} claim {claim_id}: {claim.get('fault_description') or 'No fault description recorded.'} "
                     f"Assessment result: {final_decision}. Status: {'manual review' if status_type == 'review' else status_type}.")

    result = {
        "success": True, "claim_id": claim_id, "decision": final_decision,
        "status_type": status_type, "confidence": python_prediction.get("confidence"),
        "prediction": python_prediction or None, "model_error": model_error,
        "image_model": tm_prediction or None, "tm_prediction": tm_prediction or None, "comparison": comparison or None,
        "comparison_error": comparison_error, "rules": warranty_result,
        "policy_note": "Policy checks use the project's configurable reference policies, not verified manufacturer terms. This is a recommendation, not an approval.",
        "review_reasons": list(dict.fromkeys(manual_reasons)),
        "explanation": " | ".join(explanation_parts),
        "claim_summary": claim_summary,
        "supporting_factors": list(dict.fromkeys(supporting_factors)),
        "opposing_factors": list(dict.fromkeys(opposing_factors)),
        "corrective_actions": claim.get("preparation", {}).get("actions", []) + list(manual_reasons),
        "certificate_url": f"/api/claim/{claim_id}/certificate" if pdf_path.exists() else None,
        "report_bundle_url": f"/api/claim/{claim_id}/report-bundle",
        "image_model_version": (tm_prediction or {}).get("model_version"),
        "audit_hash": reviewer_info.get("record_hash"),
    }
    result_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    (CLAIMS_DIR / claim_id / "verified_claim.json").write_text(json.dumps(claim, indent=2), encoding="utf-8")
    return jsonify(result)


# -----------------------------------------------------------------------------
# Certificate & Document Download APIs
# -----------------------------------------------------------------------------
@app.route("/api/claim/<claim_id>/certificate", methods=["GET"])
def api_download_certificate(claim_id: str):
    user = get_current_user()
    with step01.get_db() as db:
        row = db.execute("SELECT user_id, intake_actor_id, status_stage, certificate_path FROM claims WHERE claim_id=?", (claim_id,)).fetchone()
    if not row:
        abort(404)
    allowed = row["user_id"] == user["user_id"] or user["role"] == "admin" or (user["role"] == "reviewer" and row["status_stage"] in {"Manual Review", "Additional Info Required"}) or (user["role"] == "service_center" and row["intake_actor_id"] == user["user_id"])
    if not allowed:
        abort(403)
    pdf_path = OUTPUTS_DIR / (row["certificate_path"] or "missing.pdf")
    if not pdf_path.is_file():
        abort(404, description="No PDF is available for this assessment.")
    return send_file(pdf_path, as_attachment=True, download_name=f"{claim_id}-assessment.pdf")


def _authorized_claim_document(claim_id: str, mutate: bool = False):
    user = get_current_user()
    with step01.get_db() as db:
        row = db.execute("SELECT user_id,intake_actor_id,status_stage FROM claims WHERE claim_id=?", (claim_id,)).fetchone()
    if not row:
        abort(404)
    allowed = row["user_id"] == user["user_id"] or user["role"] == "admin" or (user["role"] == "reviewer" and row["status_stage"] in {"Manual Review", "Additional Info Required"}) or (user["role"] == "service_center" and row["intake_actor_id"] == user["user_id"])
    if not allowed:
        abort(403)
    if mutate and row["user_id"] != user["user_id"]:
        abort(403, description="Only the claim owner can replace or remove submitted documents.")
    if mutate and row["status_stage"] not in {"Submitted", "Additional Info Required"}:
        abort(409, description="Evidence can be changed only before assessment or while a reviewer has requested more information.")
    claims_root = CLAIMS_DIR.resolve()
    claim_root = (claims_root / claim_id).resolve()
    if claims_root not in claim_root.parents:
        abort(404)
    draft_path = claim_root / "claim_draft.json"
    if not draft_path.is_file():
        abort(404, description="Claim documents are unavailable.")
    try:
        payload = json.loads(draft_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        app.logger.exception("Could not read claim document metadata: %s", claim_id)
        abort(500, description="Claim document metadata could not be read.")
    return user, payload, draft_path


def _reset_assessment_for_requested_information(claim_id: str, prior_stage: str) -> None:
    if prior_stage != "Additional Info Required":
        return
    root = CLAIMS_DIR / claim_id
    result_path = root / "result.json"
    history_dir = root / "revisions"
    history_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if result_path.is_file():
        (history_dir / f"assessment_{stamp}.json").write_bytes(result_path.read_bytes())
        result_path.unlink()
    with step01.get_db() as db:
        row = db.execute("SELECT certificate_path FROM claims WHERE claim_id=?", (claim_id,)).fetchone()
    if row and row["certificate_path"]:
        prior_pdf = (OUTPUTS_DIR / Path(row["certificate_path"]).name).resolve()
        if OUTPUTS_DIR.resolve() in prior_pdf.parents and prior_pdf.is_file():
            (history_dir / f"assessment_{stamp}.pdf").write_bytes(prior_pdf.read_bytes())
    verified_path = root / "verified_claim.json"
    if verified_path.is_file():
        (history_dir / f"verified_claim_{stamp}.json").write_bytes(verified_path.read_bytes())
    with step01.get_db() as db:
        db.execute("UPDATE claims SET status='Submitted',status_stage='Submitted',updated_at=? WHERE claim_id=? AND status_stage='Additional Info Required'",
                   (datetime.now(timezone.utc).isoformat(), claim_id))
        db.commit()


def _archive_evidence_revision(root: Path, record: Dict[str, Any]) -> Optional[Path]:
    source = (root / Path(record.get("path", "")).name).resolve()
    if root not in source.parents or not source.is_file():
        return None
    history = root / "revisions" / "evidence"
    history.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = history / f"{record.get('document_type','document')}_{stamp}_{Path(record.get('filename') or source.name).name}"
    shutil.copy2(source, destination)
    return source


def _refresh_claim_preparation(payload: Dict[str, Any]) -> None:
    required = find_policy_for_category(payload.get("category", "")).get("mandatory_documents", [])
    available = set(payload.get("documents", {}))
    missing = [key for key in required if key not in available]
    payload.setdefault("preparation", {})["missing_documents"] = [key.replace("_", " ").title() for key in missing]
    actions = [f"Add a {key.replace('_', ' ')}." for key in missing]
    actions.extend(payload.get("serial_mismatches", []))
    if payload.get("document_duplicate_found"):
        actions.append("Review the duplicate evidence warning.")
    payload["preparation"]["actions"] = actions


@app.get("/api/claim/<claim_id>/documents")
def api_claim_documents(claim_id: str):
    _, payload, _ = _authorized_claim_document(claim_id)
    docs = [{"document_type": key, "filename": value.get("filename", "document"),
             "size_bytes": value.get("size_bytes", 0), "duplicate": bool(value.get("duplicate"))}
            for key, value in payload.get("documents", {}).items()]
    return jsonify(success=True, claim_id=claim_id, documents=docs)


@app.get("/api/claim/<claim_id>/documents/<document_type>")
def api_download_claim_document(claim_id: str, document_type: str):
    if document_type not in CLAIM_DOCUMENT_TYPES:
        abort(404)
    _, payload, _ = _authorized_claim_document(claim_id)
    record = payload.get("documents", {}).get(document_type)
    if not record:
        abort(404, description="That document is not attached to this claim.")
    root = (CLAIMS_DIR / claim_id).resolve()
    path = (root / Path(record.get("path", "")).name).resolve()
    if root not in path.parents or not path.is_file():
        abort(404, description="The stored document is unavailable.")
    return send_file(path, as_attachment=True, download_name=record.get("filename") or path.name)


@app.put("/api/claim/<claim_id>/documents/<document_type>")
@app.post("/api/claim/<claim_id>/documents/<document_type>")
@serialized
def api_replace_claim_document(claim_id: str, document_type: str):
    if document_type not in CLAIM_DOCUMENT_TYPES:
        abort(404)
    user, payload, draft_path = _authorized_claim_document(claim_id, mutate=True)
    with step01.get_db() as db:
        prior = db.execute("SELECT status_stage FROM claims WHERE claim_id=?", (claim_id,)).fetchone()
    old = payload.get("documents", {}).get(document_type)
    if request.method == "PUT" and not old:
        abort(404, description="That document is not attached to this claim.")
    if request.method == "POST" and old:
        abort(409, description="That document type already exists. Replace the existing file instead.")
    file_obj = request.files.get("file")
    if not file_obj or not file_obj.filename:
        abort(400, description="Choose a replacement file.")
    filename = secure_filename(file_obj.filename)
    suffix = Path(filename).suffix.lower()
    allowed = {".png", ".jpg", ".jpeg", ".pdf", ".webp", ".bmp", ".tiff", ".mp4", ".mov", ".webm"}
    if suffix not in allowed:
        abort(400, description="Use an image, PDF, or supported video document.")
    root = (CLAIMS_DIR / claim_id).resolve()
    if old:
        _archive_evidence_revision(root, old)
    target = (root / f"{document_type}_{filename}").resolve()
    if root not in target.parents:
        abort(400, description="The document filename is not safe.")
    file_obj.save(target)
    digest = step03.sha256_file(target)
    registry = step03.load_registry()
    existing_hash = registry.get(digest)
    duplicate = bool(existing_hash and existing_hash.get("claim_id") != claim_id)
    if not duplicate:
        registry[digest] = {"claim_id": claim_id, "document_type": document_type, "filename": filename,
                            "detected_at": datetime.now(timezone.utc).isoformat()}
    step03.save_registry(registry)
    previous = (root / Path((old or {}).get("path", "")).name).resolve()
    if old and root in previous.parents and previous.is_file() and previous != target:
        previous.unlink()
    record = {"document_type": document_type, "filename": filename, "path": str(target), "sha256": digest,
              "duplicate": duplicate, "size_bytes": target.stat().st_size}
    payload["documents"][document_type] = record
    payload["document_duplicate_found"] = any(item.get("duplicate") for item in payload["documents"].values())
    payload["document_fingerprints"] = [item for item in payload.get("document_fingerprints", []) if item.get("document_type") != document_type]
    payload["document_fingerprints"].append(record)
    _refresh_claim_preparation(payload)
    payload["status"] = "Evidence updated"
    draft_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _reset_assessment_for_requested_information(claim_id, prior["status_stage"])
    verified = root / "verified_claim.json"
    if verified.exists():
        try:
            claim = json.loads(verified.read_text(encoding="utf-8")); claim.setdefault("documents", {})[document_type] = record
            verified.write_text(json.dumps(claim, indent=2), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            app.logger.exception("Could not synchronize replacement evidence to verified claim %s", claim_id)
    event_type = "document_replaced" if old else "document_added"
    record_claim_event(claim_id, get_current_user()["user_id"], event_type, {"document_type": document_type, "sha256": digest})
    if duplicate:
        record_anomaly("duplicate_documents", "high", {"document_type": document_type}, user["user_id"], claim_id)
    return jsonify(success=True, document={"document_type": document_type, "filename": filename, "size_bytes": target.stat().st_size, "duplicate": duplicate})


@app.delete("/api/claim/<claim_id>/documents/<document_type>")
@serialized
def api_remove_claim_document(claim_id: str, document_type: str):
    if document_type not in CLAIM_DOCUMENT_TYPES:
        abort(404)
    user, payload, draft_path = _authorized_claim_document(claim_id, mutate=True)
    with step01.get_db() as db:
        prior = db.execute("SELECT status_stage FROM claims WHERE claim_id=?", (claim_id,)).fetchone()
    record = payload.get("documents", {}).get(document_type)
    if not record:
        abort(404, description="That document is not attached to this claim.")
    root = (CLAIMS_DIR / claim_id).resolve()
    path = (root / Path(record.get("path", "")).name).resolve()
    _archive_evidence_revision(root, record)
    if root in path.parents and path.is_file():
        path.unlink()
    del payload["documents"][document_type]
    payload["document_duplicate_found"] = any(item.get("duplicate") for item in payload["documents"].values())
    payload["document_fingerprints"] = [item for item in payload.get("document_fingerprints", []) if item.get("document_type") != document_type]
    _refresh_claim_preparation(payload)
    payload["status"] = "Evidence updated"
    draft_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _reset_assessment_for_requested_information(claim_id, prior["status_stage"])
    verified = root / "verified_claim.json"
    if verified.exists():
        try:
            claim = json.loads(verified.read_text(encoding="utf-8")); claim.get("documents", {}).pop(document_type, None)
            verified.write_text(json.dumps(claim, indent=2), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            app.logger.exception("Could not synchronize removed evidence to verified claim %s", claim_id)
    record_claim_event(claim_id, get_current_user()["user_id"], "document_removed", {"document_type": document_type, "sha256": record.get("sha256")})
    return jsonify(success=True)


@app.get("/api/claim/<claim_id>/report-bundle")
def api_claim_report_bundle(claim_id: str):
    _, payload, _ = _authorized_claim_document(claim_id)
    root = (CLAIMS_DIR / claim_id).resolve()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        result_path = OUTPUTS_DIR / f"{claim_id}_result.json"
        pdf_record = None
        with step01.get_db() as db:
            row = db.execute("SELECT certificate_path FROM claims WHERE claim_id=?", (claim_id,)).fetchone()
        if row and row["certificate_path"]:
            pdf_record = OUTPUTS_DIR / Path(row["certificate_path"]).name
        if pdf_record and pdf_record.is_file():
            archive.write(pdf_record, f"{claim_id}/assessment.pdf")
        elif result_path.is_file():
            archive.writestr(f"{claim_id}/assessment.json", result_path.read_bytes())
        for doc_type, record in payload.get("documents", {}).items():
            path = (root / Path(record.get("path", "")).name).resolve()
            if root in path.parents and path.is_file():
                archive.write(path, f"{claim_id}/evidence/{doc_type}-{Path(record.get('filename') or path.name).name}")
        revision_root = root / "revisions"
        if revision_root.is_dir():
            for revision in revision_root.rglob("*"):
                if revision.is_file():
                    archive.write(revision, f"{claim_id}/history/{revision.relative_to(revision_root).as_posix()}")
        archive.writestr(f"{claim_id}/manifest.json", json.dumps({"claim_id": claim_id, "documents": [{"document_type": key, "filename": item.get("filename"), "sha256": item.get("sha256")} for key, item in payload.get("documents", {}).items()]}, indent=2))
    buffer.seek(0)
    return send_file(buffer, mimetype="application/zip", as_attachment=True, download_name=f"{claim_id}-evidence.zip")



@app.get("/api/claims")
def api_list_claims():
    user = get_current_user()
    if user["role"] != "user":
        abort(403, description="This claim ledger is for user accounts.")
    query = request.args.get("q", "").strip()
    try:
        page_number = max(1, int(request.args.get("page", "1")))
        limit = min(200, max(1, int(request.args.get("limit", "50"))))
    except ValueError:
        abort(400, description="Page and limit must be whole numbers.")
    with step01.get_db() as db:
        clause = "c.user_id=?"
        params: List[Any] = [user["user_id"]]
        for name, column in (("category", "c.category"), ("status", "c.status_stage"), ("risk", "c.risk_level"), ("product_id", "c.product_id"), ("serial", "c.serial_number")):
            value = request.args.get(name, "").strip()
            if value:
                clause += f" AND {column} LIKE ?"; params.append(f"%{value}%")
        if query:
            clause += " AND (c.claim_id LIKE ? OR c.product_id LIKE ? OR c.category LIKE ? OR c.claim_title LIKE ? OR c.serial_number LIKE ? OR c.status LIKE ? OR c.status_stage LIKE ? OR c.risk_level LIKE ?)"
            params.extend([f"%{query}%"] * 8)
        date_from = normalize_date(request.args.get("date_from")); date_to = normalize_date(request.args.get("date_to"))
        if date_from:
            clause += " AND substr(c.created_at,1,10)>=?"; params.append(date_from)
        if date_to:
            clause += " AND substr(c.created_at,1,10)<=?"; params.append(date_to)
        total = db.execute(f"SELECT COUNT(*) AS count FROM claims c WHERE {clause}", params).fetchone()["count"]
        pending_actions = db.execute("SELECT COUNT(*) AS count FROM claims WHERE user_id=? AND status_stage IN ('Submitted','Under Evaluation','Additional Info Required','Manual Review')", (user["user_id"],)).fetchone()["count"]
        rows = db.execute(f"SELECT c.*,w.expiry_date AS warranty_expiry_date FROM claims c LEFT JOIN warranties w ON w.warranty_id=(SELECT w2.warranty_id FROM warranties w2 WHERE w2.product_id=c.product_id AND w2.user_id=c.user_id ORDER BY w2.start_date DESC,w2.created_at DESC LIMIT 1) WHERE {clause} ORDER BY c.created_at DESC LIMIT ? OFFSET ?",
                          [*params, limit, (page_number-1)*limit]).fetchall()
    claims = [dict(row) for row in rows]
    for claim in claims:
        expiry = claim.get("warranty_expiry_date")
        days = (date.fromisoformat(expiry) - date.today()).days if expiry else None
        claim["warranty_status"] = "Expired" if days is not None and days < 0 else "Near expiry" if days is not None and days <= 30 else "Active" if days is not None else "Not recorded"
        claim["documents_count"] = 0
        claim["missing_documents"] = []
        claim["pending_actions"] = []
        draft_path = CLAIMS_DIR / claim["claim_id"] / "claim_draft.json"
        if draft_path.is_file():
            try:
                draft = json.loads(draft_path.read_text(encoding="utf-8"))
                document_keys = set(draft.get("documents", {}))
                claim["documents_count"] = len(document_keys)
                mandatory = find_policy_for_category(claim["category"]).get("mandatory_documents", [])
                claim["missing_documents"] = [item.replace("_", " ").title() for item in mandatory if item not in document_keys]
                claim["pending_actions"].extend(draft.get("preparation", {}).get("actions", []))
                if draft.get("serial_mismatches"):
                    claim["pending_actions"].extend(draft["serial_mismatches"])
                if draft.get("fault_date"):
                    period = int(find_policy_for_category(claim["category"]).get("claim_reporting_period_days", 30))
                    claim["reporting_deadline"] = (date.fromisoformat(draft["fault_date"]) + timedelta(days=period)).isoformat()
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                app.logger.exception("Customer claim overview could not read draft %s", claim["claim_id"])
        if claim["status_stage"] == "Additional Info Required":
            claim["pending_actions"].append(claim.get("reviewer_comment") or "Check the reviewer request and add the requested evidence.")
    return jsonify(success=True, claims=claims, total=total, pending_actions=pending_actions, page=page_number, limit=limit)


def _staff_claim_query(scope: str = "", scope_params: tuple = ()):
    fields = {"claim_id": "c.claim_id", "product_id": "c.product_id", "category": "c.category",
              "serial": "c.serial_number", "status": "c.status_stage", "risk": "c.risk_level",
              "reviewer": "c.reviewer_override"}
    where, params = ([scope] if scope else []), list(scope_params)
    for name, column in fields.items():
        value = request.args.get(name, "").strip()
        if value:
            where.append(f"{column} LIKE ?")
            params.append(f"%{value}%")
    query = request.args.get("q", "").strip()
    if query:
        where.append("(c.claim_id LIKE ? OR c.product_id LIKE ? OR c.category LIKE ? OR c.claim_title LIKE ? OR c.serial_number LIKE ?)")
        params.extend([f"%{query}%"] * 5)
    date_from = normalize_date(request.args.get("date_from"))
    date_to = normalize_date(request.args.get("date_to"))
    if date_from:
        where.append("substr(c.created_at,1,10) >= ?"); params.append(date_from)
    if date_to:
        where.append("substr(c.created_at,1,10) <= ?"); params.append(date_to)
    for name, operator in (("confidence_min", ">="), ("confidence_max", "<=")):
        raw = request.args.get(name)
        if raw not in (None, ""):
            value = parse_number(raw, name)
            if value > 1:
                abort(400, description="Confidence filters must be between 0 and 1.")
            where.append(f"c.confidence {operator} ?"); params.append(value)
    warranty_status = request.args.get("warranty_status", "").lower()
    if warranty_status in {"active", "expired", "near_expiry"}:
        if warranty_status == "expired": condition = "w.expiry_date < date('now')"
        elif warranty_status == "near_expiry": condition = "w.expiry_date >= date('now') AND w.expiry_date <= date('now','+30 day')"
        else: condition = "w.expiry_date > date('now','+30 day')"
        where.append(condition)
    try:
        page_number = max(1, int(request.args.get("page", "1")))
        limit = min(200, max(1, int(request.args.get("limit", "50"))))
    except ValueError:
        abort(400, description="Page and limit must be whole numbers.")
    clause = " AND ".join(where) if where else "1=1"
    with step01.get_db() as db:
        latest_warranty = "w.warranty_id=(SELECT w2.warranty_id FROM warranties w2 WHERE w2.product_id=c.product_id AND w2.user_id=c.user_id ORDER BY w2.start_date DESC,w2.created_at DESC LIMIT 1)"
        total = db.execute(f"SELECT COUNT(*) AS count FROM claims c LEFT JOIN warranties w ON {latest_warranty} WHERE {clause}", params).fetchone()["count"]
        rows = db.execute(f"SELECT c.* FROM claims c LEFT JOIN warranties w ON {latest_warranty} WHERE {clause} ORDER BY c.created_at DESC LIMIT ? OFFSET ?", [*params, limit, (page_number-1)*limit]).fetchall()
    return [dict(row) for row in rows], total, page_number, limit


@app.get("/api/reviewer/claims")
def api_reviewer_claims():
    guard = require_role("reviewer")
    if guard:
        return guard
    claims, total, page_number, limit = _staff_claim_query("c.status_stage IN ('Manual Review','Additional Info Required')")
    return jsonify(success=True, claims=claims, total=total, page=page_number, limit=limit)


@app.get("/api/admin/claims")
def api_admin_claims():
    guard = require_role("admin")
    if guard:
        return guard
    claims, total, page_number, limit = _staff_claim_query()
    return jsonify(success=True, claims=claims, total=total, page=page_number, limit=limit)


@app.route("/api/reviewer/decision", methods=["POST"])
@serialized
def api_reviewer_submit_decision():
    """Adjudicate claim. Requires the reviewer role."""
    guard = require_role("reviewer")
    if guard:
        return guard

    data = request.get_json(silent=True) or request.form.to_dict()
    claim_id = data.get("claim_id", "")
    decision_type = data.get("decision", "approve").lower()
    reason = data.get("reason", "").strip()
    reviewer_obj = get_current_user()
    reviewer_name = reviewer_obj.get("name", data.get("reviewer", "Reviewer"))

    if not reason or len(reason) < 20:
        return jsonify({"success": False, "error": "Minimum 20 characters required in decision reason."}), 400

    decision_map = {
        "approve": "Approved",
        "reject": "Rejected",
        "request": "Additional Info Required",
        "override": "AI Overridden",
        "close": "Closed",
    }
    decision_text = decision_map.get(decision_type, decision_type.capitalize())
    stage_map = {
        "Approved": "Approved",
        "Rejected": "Rejected",
        "Additional Info Required": "Additional Info Required",
        "Closed": "Closed",
        "AI Overridden": "Manual Review",
    }
    new_stage = stage_map.get(decision_text, "Manual Review")

    if decision_type not in decision_map:
        abort(400, description="Choose a supported review action.")
    with step01.get_db() as db:
        claim_row = db.execute("SELECT user_id,certificate_path,automated_decision,status_stage FROM claims WHERE claim_id=?", (claim_id,)).fetchone()
        prediction_row = db.execute("SELECT * FROM prediction_records WHERE claim_id=?", (claim_id,)).fetchone()
        if not claim_row:
            abort(404, description="Claim not found.")
        if claim_row["status_stage"] not in {"Manual Review", "Additional Info Required"}:
            abort(409, description="Only claims in reviewer assessment or awaiting requested information can be adjudicated.")
        if new_stage not in _STATUS_TRANSITIONS.get(claim_row["status_stage"], set()):
            abort(409, description="That claim status transition is not allowed.")

    # Append-only audit trail
    record = step10.append_audit_record({
        "event_id": "AUD-" + secrets.token_hex(6).upper(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "claim_id": claim_id,
        "automated_decision": claim_row["automated_decision"] or "Not recorded",
        "original_prediction_record": dict(prediction_row) if prediction_row else None,
        "reviewer": reviewer_name,
        "action": decision_text,
        "reason": reason,
        "source": "AssureX Reviewer Portal",
    })

    # Update DB: status, stage, reviewer comment
    with step01.get_db() as db:
        db.execute(
            "UPDATE claims SET status = ?, status_stage = ?, decision = ?, reviewer_comment = ?, reviewer_override = ?, updated_at = ? WHERE claim_id = ? AND status_stage = ?",
            (decision_text, new_stage, decision_text, reason,
             reviewer_name, datetime.now(timezone.utc).isoformat(), claim_id, claim_row["status_stage"]),
        )
        db.commit()
    record_claim_event(claim_id, claim_row["user_id"], "review_decision", {
        "automated_decision": claim_row["automated_decision"], "decision": decision_text,
        "reviewer": reviewer_name, "reason": reason,
    })
    push_notification(claim_row["user_id"], claim_id, f"Reviewer decision on {claim_id}: {decision_text}")
    result_path = CLAIMS_DIR / claim_id / "result.json"
    claim_path = CLAIMS_DIR / claim_id / "verified_claim.json"
    if claim_row["certificate_path"] and result_path.is_file() and claim_path.is_file():
        try:
            original = json.loads(result_path.read_text(encoding="utf-8"))
            original_decision = {
                "claim_id": claim_id, "decision": original.get("decision"),
                "explanation": original.get("explanation"),
                "ai_results": {"python": original.get("prediction"),
                               "image_model": original.get("image_model", original.get("tm_prediction")),
                               "comparison": original.get("comparison")},
                "warranty": original.get("rules"),
            }
            pdf_path = OUTPUTS_DIR / claim_row["certificate_path"]
            step10.build_pdf(pdf_path, original_decision,
                             json.loads(claim_path.read_text(encoding="utf-8")),
                             {"reviewer": reviewer_name, "action": decision_text,
                              "reason": reason, "record_hash": record.get("record_hash")})
        except Exception:
            app.logger.exception("Updated reviewer report could not be generated")

    return jsonify({
        "success": True,
        "claim_id": claim_id,
        "decision": decision_text,
        "status_stage": new_stage,
        "record_hash": record.get("record_hash"),
    })


# -----------------------------------------------------------------------------
# Service Center APIs
# -----------------------------------------------------------------------------
@app.route("/api/service-center/claims", methods=["GET"])
def api_service_center_claims():
    """Return the service-center work queue to service-center staff only."""
    guard = require_role("service_center")
    if guard:
        return guard
    actor = get_current_user()
    claims, total, page_number, limit = _staff_claim_query("c.intake_actor_id=?", (actor["user_id"],))
    claims = [{key: row.get(key) for key in ("claim_id", "product_id", "category", "claim_title", "serial_number", "status", "status_stage", "risk_level", "created_at")} for row in claims]
    return jsonify({"success": True, "claims": claims, "total": total, "page": page_number, "limit": limit})


@app.post("/api/service-center/claims/<claim_id>/repairs")
def api_service_center_record_repair(claim_id: str):
    """Attach a documented service visit to the product behind a claim."""
    guard = require_role("service_center")
    if guard:
        return guard
    actor = get_current_user()
    data = request.get_json(silent=True) or {}
    repair_date = normalize_date(data.get("repair_date"))
    center = str(data.get("service_center", "")).strip()
    parts = str(data.get("parts_replaced", "")).strip()
    outcome = str(data.get("outcome", "")).strip()
    cost = parse_number(data.get("cost", 0), "repair cost")
    if not repair_date or not center or not outcome:
        abort(400, description="Enter a valid repair date, service center, and repair outcome.")
    if date.fromisoformat(repair_date) > date.today():
        abort(400, description="Repair date cannot be in the future.")
    with step01.get_db() as db:
        claim = db.execute("SELECT claim_id,user_id,product_id,intake_actor_id FROM claims WHERE claim_id=?", (claim_id,)).fetchone()
        if not claim:
            abort(404, description="Claim not found.")
        if claim["intake_actor_id"] != actor["user_id"]:
            abort(403, description="This service record was not created by your service-center account.")
        if not claim["product_id"]:
            abort(409, description="This claim has no registered product to attach a repair record to.")
        repair_id = "RPR-" + secrets.token_hex(5).upper()
        created = datetime.now(timezone.utc).isoformat()
        db.execute("INSERT INTO repairs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (repair_id, claim["product_id"], claim["user_id"], repair_date, center, parts,
                    outcome, cost, int(parse_bool(data.get("authorized"))), None, created))
        db.commit()
    record_application_event(actor["user_id"], "repair", repair_id, "recorded_by_service_center", {
        "claim_id": claim_id, "product_id": claim["product_id"], "product_owner": claim["user_id"],
        "service_center": center, "authorized": parse_bool(data.get("authorized")),
    })
    push_notification(claim["user_id"], claim_id, f"A repair record was added to the product linked to {claim_id}.")
    return jsonify(success=True, repair_id=repair_id, claim_id=claim_id), 201


# -----------------------------------------------------------------------------
# Contact Form API
# -----------------------------------------------------------------------------
@app.route("/api/contact", methods=["POST"])
def api_contact():
    user = get_optional_user()
    data = request.get_json(silent=True) or request.form.to_dict()
    message = str(data.get("message", "")).strip()
    if not message:
        abort(400, description="Enter a support message.")
    with step01.get_db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS support_requests (id INTEGER PRIMARY KEY, user_id TEXT, message TEXT, created_at TEXT)")
        db.execute("INSERT INTO support_requests(user_id,message,created_at) VALUES(?,?,?)", (user["user_id"] if user else None, message, datetime.now(timezone.utc).isoformat()))
        db.commit()
    return jsonify(success=True)


# -----------------------------------------------------------------------------
# Notifications API
# -----------------------------------------------------------------------------
@app.route("/api/notifications", methods=["GET"])
def api_notifications():
    user = get_current_user()
    notes: List[Dict[str, Any]] = []
    try:
        with step01.get_db() as db:
            rows = db.execute(
                "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
                (user["user_id"],),
            ).fetchall()
            notes = [dict(r) for r in rows]
    except step01.DatabaseError:
        app.logger.exception("Could not load notifications for user %s", user["user_id"])
        return jsonify(success=False, error="Notifications could not be loaded."), 500
    return jsonify({"success": True, "notifications": notes, "unread_count": sum(1 for n in notes if not n.get("is_read"))})


def create_expiry_notifications() -> int:
    """Scheduled, idempotent alert generation for warranties approaching expiry."""
    created = 0
    with step01.get_db() as db:
        lead_row = db.execute("SELECT setting_value FROM application_settings WHERE setting_key='warranty_expiry_lead_days'").fetchone()
        lead = int(lead_row["setting_value"]) if lead_row else 30
        warranties = db.execute("SELECT w.user_id,w.product_id,w.expiry_date,p.product_name FROM warranties w JOIN products p USING(product_id) WHERE w.expiry_date>=date('now') AND w.expiry_date<=date('now',?)",
                               (f"+{lead} day",)).fetchall()
        for warranty in warranties:
            message_text = f"Warranty for {warranty['product_name']} expires on {warranty['expiry_date']}."
            found = db.execute("SELECT 1 FROM notifications WHERE user_id=? AND claim_id=? AND message=?",
                               (warranty["user_id"], warranty["product_id"], message_text)).fetchone()
            if not found:
                db.execute("INSERT INTO notifications(user_id,claim_id,message,created_at) VALUES(?,?,?,?)",
                           (warranty["user_id"], warranty["product_id"], message_text, datetime.now(timezone.utc).isoformat()))
                created += 1
        pending_claims = db.execute("SELECT claim_id,user_id,category,fault_description,status_stage FROM claims WHERE status_stage NOT IN ('Approved','Rejected','Closed')").fetchall()
        for claim in pending_claims:
            draft_path = CLAIMS_DIR / claim["claim_id"] / "claim_draft.json"
            if not draft_path.is_file():
                continue
            try:
                draft = json.loads(draft_path.read_text(encoding="utf-8"))
                policy = find_policy_for_category(claim["category"])
                limit_days = int(policy.get("claim_reporting_period_days", policy.get("reporting_period", {}).get("days", 30)))
                fault_day = date.fromisoformat(draft.get("fault_date", ""))
                due_day = fault_day + timedelta(days=limit_days)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            days_left = (due_day - date.today()).days
            if -1 <= days_left <= 3:
                urgency = "due today" if days_left == 0 else (f"overdue by {abs(days_left)} day(s)" if days_left < 0 else f"due in {days_left} day(s)")
                message_text = f"Claim {claim['claim_id']} reporting window is {urgency}. Contact the reviewer if you need help."
                found = db.execute("SELECT 1 FROM notifications WHERE user_id=? AND claim_id=? AND message=?", (claim["user_id"], claim["claim_id"], message_text)).fetchone()
                if not found:
                    db.execute("INSERT INTO notifications(user_id,claim_id,message,created_at) VALUES(?,?,?,?)", (claim["user_id"], claim["claim_id"], message_text, datetime.now(timezone.utc).isoformat()))
                    created += 1
        db.execute("INSERT INTO application_settings(setting_key,setting_value) VALUES('expiry_scheduler_last_run',?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value",
                   (datetime.now(timezone.utc).isoformat(),))
        db.commit()
    return created


def expiry_scheduler(stop_event: threading.Event) -> None:
    """Run once at startup, then on a daily interval; one thread per app process."""
    interval = max(60, int(os.environ.get("WARRANTY_ALERT_SCHEDULER_INTERVAL", str(24 * 60 * 60))))
    while not stop_event.is_set():
        try:
            create_expiry_notifications()
        except Exception:
            app.logger.exception("Scheduled warranty alerts failed")
        if stop_event.wait(interval):
            return


@app.get("/api/admin/anomalies")
def api_admin_anomalies():
    guard = require_role("admin")
    if guard:
        return guard
    limit = min(100, max(1, request.args.get("limit", 50, type=int)))
    with step01.get_db() as db:
        rows = db.execute("SELECT id,event_type,severity,actor_id,entity_id,details,created_at,acknowledged_at,acknowledged_by FROM anomaly_events ORDER BY acknowledged_at IS NULL DESC,created_at DESC LIMIT ?", (limit,)).fetchall()
    return jsonify(success=True, events=[{**dict(row), "details": json.loads(row["details"])} for row in rows])


@app.post("/api/admin/anomalies/<int:event_id>/acknowledge")
def api_admin_acknowledge_anomaly(event_id: int):
    guard = require_role("admin")
    if guard:
        return guard
    actor = get_current_user()
    with step01.get_db() as db:
        changed = db.execute("UPDATE anomaly_events SET acknowledged_at=?,acknowledged_by=? WHERE id=? AND acknowledged_at IS NULL",
                             (datetime.now(timezone.utc).isoformat(), actor["user_id"], event_id)).rowcount
        db.commit()
    if not changed:
        abort(404, description="Unacknowledged alert not found.")
    record_application_event(actor["user_id"], "anomaly", str(event_id), "acknowledged", {})
    return jsonify(success=True)


@app.get("/api/service-center/customers")
def api_service_center_customers():
    guard = require_role("service_center")
    if guard:
        return guard
    query = request.args.get("q", "").strip().lower()
    if len(query) < 3:
        abort(400, description="Enter at least three characters of the customer email.")
    with step01.get_db() as db:
        users = db.execute("SELECT user_id,name,email FROM users WHERE role='user' AND lower(email) LIKE ? ORDER BY email LIMIT 20", (f"%{query}%",)).fetchall()
        results = []
        for customer in users:
            products = db.execute("SELECT product_id,product_name,category,brand,model,serial_number,purchase_date,warranty_months FROM products WHERE user_id=? ORDER BY product_name", (customer["user_id"],)).fetchall()
            results.append({"user_id": customer["user_id"], "name": customer["name"], "email": customer["email"], "products": [dict(product) for product in products]})
    return jsonify(success=True, customers=results)


@app.route("/api/admin/settings", methods=["GET", "PUT"])
def api_admin_settings():
    guard = require_role("admin")
    if guard:
        return guard
    if request.method == "PUT":
        data = request.get_json(silent=True) or {}
        try:
            lead = int(data.get("warranty_expiry_lead_days"))
        except (TypeError, ValueError):
            abort(400, description="Enter a whole number of days.")
        if not 1 <= lead <= 365:
            abort(400, description="Expiry alerts must be set between 1 and 365 days.")
        with step01.get_db() as db:
            db.execute("UPDATE application_settings SET setting_value=? WHERE setting_key='warranty_expiry_lead_days'", (str(lead),))
            db.commit()
        record_application_event(get_current_user()["user_id"], "settings", "warranty_expiry_lead_days",
                                 "updated", {"days": lead})
    with step01.get_db() as db:
        lead = int(db.execute("SELECT setting_value FROM application_settings WHERE setting_key='warranty_expiry_lead_days'").fetchone()["setting_value"])
        last = db.execute("SELECT setting_value FROM application_settings WHERE setting_key='expiry_scheduler_last_run'").fetchone()
    return jsonify(success=True, settings={"warranty_expiry_lead_days": lead,
                                            "expiry_scheduler_last_run": last["setting_value"] if last else None,
                                            "expiry_scheduler_interval_seconds": max(60, int(os.environ.get("WARRANTY_ALERT_SCHEDULER_INTERVAL", str(24*60*60))))})


@app.route("/api/notifications/read", methods=["POST"])
def api_mark_notifications_read():
    user = get_current_user()
    try:
        with step01.get_db() as db:
            db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user["user_id"],))
            db.commit()
    except step01.DatabaseError:
        app.logger.exception("Could not mark notifications read for user %s", user["user_id"])
        return jsonify(success=False, error="Notifications could not be updated."), 500
    return jsonify({"success": True})


# -----------------------------------------------------------------------------
# Admin Analytics & Export APIs
# -----------------------------------------------------------------------------
@app.route("/api/admin/analytics", methods=["GET"])
def api_admin_analytics():
    guard = require_role("admin")
    if guard:
        return guard
    try:
        with step01.get_db() as db:
            total = db.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
            valid_recommendations = db.execute("SELECT COUNT(*) AS c FROM claims WHERE automated_decision='Likely Valid'").fetchone()["c"]
            invalid_recommendations = db.execute("SELECT COUNT(*) AS c FROM claims WHERE automated_decision='Likely Invalid'").fetchone()["c"]
            manual_recommendations = db.execute("SELECT COUNT(*) AS c FROM claims WHERE automated_decision='Manual Review Required'").fetchone()["c"]
            approved = db.execute("SELECT COUNT(*) as c FROM claims WHERE status = 'Approved'").fetchone()["c"]
            rejected = db.execute("SELECT COUNT(*) as c FROM claims WHERE status = 'Rejected'").fetchone()["c"]
            review = db.execute("SELECT COUNT(*) as c FROM claims WHERE status_stage IN ('Manual Review', 'Submitted', 'Under Evaluation', 'Additional Info Required')").fetchone()["c"]
            duplicates = db.execute("SELECT COUNT(*) as c FROM claims WHERE duplicate_flag=1").fetchone()["c"]
            disagreements = db.execute("SELECT COUNT(*) as c FROM claims WHERE model_consistency='Model Disagreement'").fetchone()["c"]
            total_users = db.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
            total_products = db.execute("SELECT COUNT(*) as c FROM products").fetchone()["c"]
            avg_conf = db.execute("SELECT AVG(confidence) as c FROM claims WHERE confidence IS NOT NULL").fetchone()["c"]
            by_category = db.execute(
                "SELECT category, COUNT(*) as count FROM claims GROUP BY category ORDER BY count DESC"
            ).fetchall()
            by_stage = db.execute(
                "SELECT status_stage, COUNT(*) as count FROM claims GROUP BY status_stage"
            ).fetchall()
            by_decision = db.execute("SELECT COALESCE(automated_decision,decision,'Unassessed') AS decision,COUNT(*) AS count FROM claims GROUP BY COALESCE(automated_decision,decision,'Unassessed')").fetchall()
            by_month = db.execute("SELECT substr(created_at,1,7) AS month,COUNT(*) AS count FROM claims GROUP BY substr(created_at,1,7) ORDER BY month").fetchall()
            by_fault = db.execute("SELECT COALESCE(NULLIF(claim_title,''),'Unspecified') AS fault,COUNT(*) AS count FROM claims GROUP BY fault ORDER BY count DESC LIMIT 12").fetchall()
            rejection_reasons = db.execute("SELECT COALESCE(NULLIF(reviewer_comment,''),'No reviewer reason recorded') AS reason,COUNT(*) AS count FROM claims WHERE status='Rejected' GROUP BY reason ORDER BY count DESC LIMIT 12").fetchall()
            repairs_by_center = db.execute("SELECT service_center,COUNT(*) AS count FROM repairs GROUP BY service_center ORDER BY count DESC LIMIT 12").fetchall()
            expiry_by_month = db.execute("SELECT substr(expiry_date,1,7) AS month,COUNT(*) AS count FROM warranties GROUP BY substr(expiry_date,1,7) ORDER BY month").fetchall()
            manual_review_by_month = db.execute("SELECT substr(created_at,1,7) AS month,COUNT(*) AS count FROM claims WHERE status_stage='Manual Review' OR automated_decision='Manual Review Required' GROUP BY substr(created_at,1,7) ORDER BY month").fetchall()
            model_versions = db.execute("SELECT COALESCE(model_version,'unavailable') AS tabular_model,COALESCE(image_model_version,'unavailable') AS image_model,COUNT(*) AS count FROM prediction_records GROUP BY tabular_model,image_model ORDER BY count DESC").fetchall()
        image_metrics = {}
        metrics_path = MODELS_DIR / "claim_card_model_metrics.json"
        if metrics_path.is_file():
            try:
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                image_metrics = {"model": metrics.get("model"), "accuracy": metrics.get("accuracy"),
                                 "held_out_test_images": metrics.get("held_out_test_images"),
                                 "evaluation_data": "SRS-derived synthetic claim-card holdout"}
            except (OSError, json.JSONDecodeError):
                app.logger.exception("Image-model metrics could not be read")
        return jsonify({
            "success": True,
            "total_claims": total,
            "valid_recommendations": valid_recommendations,
            "invalid_recommendations": invalid_recommendations,
            "manual_recommendations": manual_recommendations,
            "approved": approved,
            "rejected": rejected,
            "pending_review": review,
            "duplicates": duplicates,
            "model_disagreements": disagreements,
            "total_users": total_users,
            "total_products": total_products,
            "avg_confidence": round(avg_conf, 4) if avg_conf is not None else None,
            "by_category": [dict(r) for r in by_category],
            "by_stage": [dict(r) for r in by_stage],
            "by_decision": [dict(r) for r in by_decision],
            "by_month": [dict(r) for r in by_month],
            "by_fault": [dict(r) for r in by_fault],
            "rejection_reasons": [dict(r) for r in rejection_reasons],
            "repairs_by_center": [dict(r) for r in repairs_by_center],
            "expiry_by_month": [dict(r) for r in expiry_by_month],
            "manual_review_by_month": [dict(r) for r in manual_review_by_month],
            "model_versions": [dict(r) for r in model_versions],
            "image_model_metrics": image_metrics,
        })
    except Exception:
        app.logger.exception("Admin analytics request failed")
        return jsonify({"success": False, "error": "Analytics could not be loaded. Please try again."}), 500


@app.route("/api/admin/export", methods=["GET"])
def api_admin_export():
    """Export a real application dataset as CSV. Admin only."""
    guard = require_role("admin")
    if guard:
        return guard
    import io, csv
    fieldnames = None
    try:
        with step01.get_db() as db:
            dataset = request.args.get("dataset", "claims")
            queries = {
                "claims": "SELECT * FROM claims ORDER BY created_at DESC",
                "products": "SELECT * FROM products ORDER BY purchase_date DESC",
                "warranties": "SELECT * FROM warranties ORDER BY expiry_date",
                "repairs": "SELECT * FROM repairs ORDER BY repair_date DESC",
                "audit": "SELECT * FROM application_audit_events ORDER BY created_at DESC",
            }
            if dataset == "analytics":
                rows = []
                for metric, query in (
                    ("stage", "SELECT status_stage AS dimension,COUNT(*) AS count FROM claims GROUP BY status_stage"),
                    ("outcome", "SELECT COALESCE(automated_decision,decision,'Unassessed') AS dimension,COUNT(*) AS count FROM claims GROUP BY COALESCE(automated_decision,decision,'Unassessed')"),
                    ("category", "SELECT category AS dimension,COUNT(*) AS count FROM claims GROUP BY category"),
                    ("month", "SELECT substr(created_at,1,7) AS dimension,COUNT(*) AS count FROM claims GROUP BY substr(created_at,1,7)"),
                    ("risk", "SELECT COALESCE(risk_level,'unclassified') AS dimension,COUNT(*) AS count FROM claims GROUP BY risk_level"),
                    ("fault", "SELECT COALESCE(NULLIF(claim_title,''),'Unspecified') AS dimension,COUNT(*) AS count FROM claims GROUP BY dimension"),
                    ("rejection_reason", "SELECT COALESCE(NULLIF(reviewer_comment,''),'No reviewer reason recorded') AS dimension,COUNT(*) AS count FROM claims WHERE status='Rejected' GROUP BY dimension"),
                    ("repair_center", "SELECT service_center AS dimension,COUNT(*) AS count FROM repairs GROUP BY service_center"),
                    ("warranty_expiry_month", "SELECT substr(expiry_date,1,7) AS dimension,COUNT(*) AS count FROM warranties GROUP BY dimension"),
                    ("manual_review_month", "SELECT substr(created_at,1,7) AS dimension,COUNT(*) AS count FROM claims WHERE status_stage='Manual Review' OR automated_decision='Manual Review Required' GROUP BY dimension"),
                ):
                    rows.extend({"metric": metric, **dict(row)} for row in db.execute(query))
                rows.extend([{"metric": "duplicates", "dimension": "flagged", "count": db.execute("SELECT COUNT(*) FROM claims WHERE duplicate_flag=1").fetchone()[0]},
                             {"metric": "model_disagreements", "dimension": "flagged", "count": db.execute("SELECT COUNT(*) FROM claims WHERE model_consistency='Model Disagreement'").fetchone()[0]}])
            elif dataset in queries:
                rows = [dict(row) for row in db.execute(queries[dataset])]
                if not rows:
                    table = {"claims": "claims", "products": "products", "warranties": "warranties",
                             "repairs": "repairs", "audit": "application_audit_events"}[dataset]
                    empty_columns = [row["name"] for row in db.execute(f"PRAGMA table_info({table})")]
                    fieldnames = empty_columns
            else:
                abort(400, description="Choose claims, products, warranties, repairs, audit, or analytics export.")
        output = io.StringIO()
        fieldnames = list(rows[0].keys()) if rows else fieldnames or []
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            safe = {key: ("'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value)
                    for key, value in dict(r).items()}
            writer.writerow(safe)
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=assurex_{dataset}_export.csv"},
        )
    except Exception:
        app.logger.exception("Admin export failed")
        return jsonify({"success": False, "error": "The export could not be created. Please try again."}), 500


@app.get("/api/admin/users")
def api_admin_users():
    guard = require_role("admin")
    if guard:
        return guard
    with step01.get_db() as db:
        rows = db.execute("SELECT user_id, name, email, role, created_at FROM users ORDER BY created_at DESC").fetchall()
    return jsonify(success=True, users=[dict(row) for row in rows])


@app.post("/api/admin/users")
def api_admin_create_user():
    guard = require_role("admin")
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    role = str(data.get("role", ""))
    if not name or len(name) > 120 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        abort(400, description="Enter a name and a valid email address.")
    if len(password) < 12:
        abort(400, description="Staff passwords must be at least 12 characters.")
    if role not in {"admin", "reviewer", "service_center", "user"}:
        abort(400, description="Choose one of the four supported roles.")
    user_id = "USR-" + secrets.token_hex(4).upper()
    try:
        with step01.get_db() as db:
            db.execute("INSERT INTO users (user_id,name,email,password_hash,role,created_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (user_id, name, email, step01.hash_password(password), role, date.today().isoformat()))
            db.commit()
    except step01.IntegrityError:
        return jsonify(success=False, error="An account with this email already exists."), 409
    record_application_event(get_current_user()["user_id"], "user", user_id, "account_provisioned", {"role": role})
    return jsonify(success=True, user={"user_id": user_id, "name": name, "email": email,
                                        "role": role, "created_at": date.today().isoformat()}), 201


# -----------------------------------------------------------------------------
# Global Error Handlers
# -----------------------------------------------------------------------------
@app.errorhandler(404)
def handle_404(err):
    return jsonify({"success": False, "error": "Endpoint not found.", "code": 404}), 404


@app.errorhandler(500)
def handle_500(err):
    return jsonify({"success": False, "error": "Internal server error. Please try again.", "code": 500}), 500


@app.errorhandler(403)
def handle_403(err):
    return jsonify({"success": False, "error": "Access denied.", "code": 403}), 403


# -----------------------------------------------------------------------------
# Main Application Entry Point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    stop_expiry_scheduler = threading.Event()
    threading.Thread(target=expiry_scheduler, args=(stop_expiry_scheduler,), name="assurex-expiry-alerts", daemon=True).start()
    print("=" * 68)
    print(f"ClaimSure_AI / AssureX Flask Engine running on http://127.0.0.1:{port}")
    print("Serving integrated frontend from:", FRONTEND_DIR)
    print("=" * 68)
    app.run(host="127.0.0.1", port=port, debug=False)
