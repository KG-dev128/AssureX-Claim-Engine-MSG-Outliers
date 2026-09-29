"""
app/services/policy_service.py
Warranty policy engine configuration and dynamic rules (FR xxvi).
Manages category-specific warranty parameters, excluded damage types, and documentation requirements.
"""
import os
import json
from typing import Dict, Any, List, Optional
from app.extensions import db
from app.models import WarrantyPolicy

POLICY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'policies')


def get_policy_file_path(category: str) -> str:
    category_slug = category.lower().replace(' ', '_')
    return os.path.join(POLICY_DIR, f"{category_slug}_policy.json")


def load_policy(category: str) -> Dict[str, Any]:
    """
    Load warranty policy for category.
    Priority 1: DB (warranty_policies table)
    Priority 2: policies/<category>_policy.json
    Fallback: general policy
    """
    category_slug = category.lower().replace(' ', '_')

    # 1. DB Lookup
    record = WarrantyPolicy.query.filter_by(product_category=category_slug).first()
    if record and record.policy_data:
        return record.policy_data

    # 2. File Lookup
    filepath = get_policy_file_path(category_slug)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[PolicyService] Warning reading file {filepath}: {e}")

    # Fallback to general policy
    gen_path = os.path.join(POLICY_DIR, "general_policy.json")
    if os.path.exists(gen_path):
        with open(gen_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    # Hardcoded default fallback
    return {
        "category": category_slug,
        "standard_warranty_months": 12,
        "max_claim_reporting_days": 30,
        "excluded_damage_types": ["wear_and_tear", "water_damage"],
        "required_documents": ["receipt", "fault_evidence"],
        "requires_authorized_repair_only": True,
        "max_allowable_repairs": 3,
    }


def seed_default_policies():
    """Seed or update database with JSON policies from policies/ directory."""
    if not os.path.exists(POLICY_DIR):
        return

    for fname in os.listdir(POLICY_DIR):
        if fname.endswith('_policy.json'):
            cat = fname.replace('_policy.json', '')
            filepath = os.path.join(POLICY_DIR, fname)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                existing = WarrantyPolicy.query.filter_by(product_category=cat).first()
                if not existing:
                    policy = WarrantyPolicy(
                        product_category=cat,
                        policy_data=data,
                        version='1.0',
                    )
                    db.session.add(policy)
                else:
                    existing.policy_data = data
            except Exception as e:
                print(f"[PolicyService] Error seeding {fname}: {e}")

    db.session.commit()


def update_policy(category: str, policy_data: Dict[str, Any], admin_user_id: Optional[str] = None) -> WarrantyPolicy:
    """Update or create a policy in the database."""
    category_slug = category.lower().replace(' ', '_')
    existing = WarrantyPolicy.query.filter_by(product_category=category_slug).first()

    if existing:
        existing.policy_data = policy_data
        existing.updated_by = admin_user_id
        current_ver = float(existing.version or '1.0')
        existing.version = f"{current_ver + 0.1:.1f}"
        policy = existing
    else:
        policy = WarrantyPolicy(
            product_category=category_slug,
            policy_data=policy_data,
            version='1.0',
            updated_by=admin_user_id,
        )
        db.session.add(policy)

    db.session.commit()
    return policy


def list_all_policies() -> List[Dict[str, Any]]:
    """List all configured warranty policies."""
    records = WarrantyPolicy.query.all()
    if not records:
        seed_default_policies()
        records = WarrantyPolicy.query.all()
    return [r.to_dict() for r in records]
