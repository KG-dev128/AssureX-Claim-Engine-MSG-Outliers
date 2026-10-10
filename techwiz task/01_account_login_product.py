"""
ASSUREX - STEP 1
Account Login + Product Selection

This is a small local/demo backend module. It uses SQLite so the flow is
real and easy to understand, while keeping the code simple enough to explain
to an evaluator.

Run:
    python 01_account_login_product.py

It creates/updates:
    data/assurex.db
    outputs/step01_session.json
"""

from __future__ import annotations

import argparse
import os
import hashlib
import json
import secrets
from datetime import date
from pathlib import Path

from db import DatabaseError, IntegrityError, get_db as _get_db

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("ASSUREX_DATA_DIR", BASE_DIR / "instance"))
OUTPUT_DIR = BASE_DIR / "outputs"
DB_PATH = DATA_DIR / "assurex.db"
SESSION_PATH = OUTPUT_DIR / "step01_session.json"

ROLES = {"user", "customer", "service_center", "reviewer", "admin"}


def get_db():
    """Use Neon when DATABASE_URL is configured; keep SQLite for offline tests."""
    return _get_db(DB_PATH)


def create_tables() -> None:
    with get_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                category TEXT NOT NULL,
                brand TEXT NOT NULL,
                model TEXT NOT NULL,
                serial_number TEXT NOT NULL,
                purchase_date TEXT NOT NULL,
                purchase_price REAL,
                warranty_months INTEGER NOT NULL,
                retailer TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
            """
        )
        db.commit()


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Store passwords as salted PBKDF2 hashes rather than plain text."""
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"pbkdf2_sha256$120000${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return secrets.compare_digest(derived.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def login(email: str, password: str) -> dict | None:
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user and verify_password(password, user["password_hash"]):
        return user
    return None


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def add_product(user_id: str) -> dict:
    print("\n--- Add a registered product ---")
    product = {
        "product_id": "PROD-" + secrets.token_hex(5).upper(),
        "user_id": user_id,
        "product_name": ask("Product name"),
        "category": ask("Category"),
        "brand": ask("Brand"),
        "model": ask("Model"),
        "serial_number": ask("Serial number"),
        "purchase_date": ask("Purchase date (YYYY-MM-DD)"),
        "purchase_price": float(ask("Purchase price")),
        "warranty_months": int(ask("Warranty duration in months")),
        "retailer": ask("Retailer"),
    }
    with get_db() as db:
        db.execute(
            "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(product.values()),
        )
        db.commit()
    return product


def list_products(user_id: str) -> list:
    with get_db() as db:
        return db.execute("SELECT * FROM products WHERE user_id = ? ORDER BY purchase_date DESC", (user_id,)).fetchall()


def choose_product(user_id: str) -> dict:
    products = list_products(user_id)
    if not products:
        return add_product(user_id)

    print("\nRegistered products:")
    for i, product in enumerate(products, start=1):
        print(
            f"  {i}. {product['product_name']} | {product['brand']} {product['model']} | "
            f"Serial: {product['serial_number']}"
        )
    choice = input("Select a product number, or type N for a new product: ").strip().lower()
    if choice == "n":
        return add_product(user_id)
    index = int(choice) - 1
    if index < 0 or index >= len(products):
        raise ValueError("Invalid product selection.")
    return dict(products[index])


def main() -> None:
    parser = argparse.ArgumentParser(description="AssureX Step 1 - login and product selection")
    parser.add_argument("--email", help="Login email. Interactive when omitted.")
    parser.add_argument("--password", help="Login password. Interactive when omitted.")
    parser.add_argument("--product-id", help="Select product directly without interactive menu.")
    args = parser.parse_args()

    create_tables()

    print("=" * 68)
    print("ASSUREX - STEP 1: ACCOUNT LOGIN & PRODUCT SELECTION")
    print("=" * 68)

    email = args.email or ask("Email")
    password = args.password or ask("Password")
    user = login(email, password)

    if not user:
        raise SystemExit("Login failed. Check the email/password.")
    if user["role"] not in ROLES:
        raise SystemExit("This account has an unsupported role.")

    print(f"\nWelcome, {user['name']} ({user['role']}).")
    if args.product_id:
        with get_db() as db:
            selected = db.execute(
                "SELECT * FROM products WHERE user_id = ? AND product_id = ?",
                (user["user_id"], args.product_id),
            ).fetchone()
        if not selected:
            raise SystemExit("The requested product was not found for this user.")
        product = dict(selected)
    else:
        product = choose_product(user["user_id"])

    session = {
        "user_id": user["user_id"],
        "user_name": user["name"],
        "role": user["role"],
        "claim_action": "File a Claim",
        "selected_product": product,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(json.dumps(session, indent=2), encoding="utf-8")

    print(f"\nProduct selected: {product['product_name']}")
    print(f"Session saved to: {SESSION_PATH}")


if __name__ == "__main__":
    main()
