"""Create the first AssureX administrator interactively; never seeds credentials."""
from __future__ import annotations

import getpass
import importlib
import re
import secrets
from datetime import date

accounts = importlib.import_module("01_account_login_product")


def main() -> None:
    accounts.create_tables()
    with accounts.get_db() as db:
        if db.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone():
            raise SystemExit("An administrator already exists. Sign in and provision accounts from Admin.")
    name = input("Administrator name: ").strip()
    email = input("Administrator email: ").strip().lower()
    password = getpass.getpass("Password (12 characters minimum): ")
    confirm = getpass.getpass("Confirm password: ")
    if not name or len(name) > 120 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise SystemExit("Enter a name and valid email address.")
    if len(password) < 12 or password != confirm:
        raise SystemExit("Passwords must match and contain at least 12 characters.")
    user_id = "USR-" + secrets.token_hex(4).upper()
    with accounts.get_db() as db:
        db.execute("INSERT INTO users (user_id,name,email,password_hash,role,created_at) VALUES (?, ?, ?, ?, ?, ?)",
                   (user_id, name, email, accounts.hash_password(password), "admin", date.today().isoformat()))
        db.commit()
    print(f"Administrator account created for {email}. Start the app and sign in.")


if __name__ == "__main__":
    main()
