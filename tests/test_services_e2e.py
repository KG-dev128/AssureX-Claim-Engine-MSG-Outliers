"""
tests/test_services_e2e.py
End-to-End Service Integration Test.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from datetime import date, timedelta
from app import create_app
from app.extensions import db
from app.models import User, Product, Warranty, Claim
from app.services import (
    register_user,
    seed_default_policies,
    generate_claim_summary_card,
    evaluate_warranty_rules,
    predict_claim,
    predict_gtm,
    evaluate_final_decision,
    generate_claim_pdf_report
)

def run_test():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        seed_default_policies()

        # 1. Register User
        ok, u = register_user({
            'username': 'e2e_user',
            'email': 'e2e@test.com',
            'password': 'Password123!',
            'role': 'customer'
        })
        assert ok, "User registration failed"
        user_id = u['user_id']

        # 2. Register Product
        prod = Product(
            user_id=user_id,
            product_name='Samsung QLED 65',
            category='electronics',
            brand='Samsung',
            model_number='QN65Q80B',
            serial_number='SN-987654321',
            purchase_date=date.today() - timedelta(days=90),
            purchase_price=1299.99,
            warranty_duration_months=24
        )
        db.session.add(prod)
        db.session.flush()

        # 3. Create Warranty
        warr = Warranty(
            product_id=prod.product_id,
            warranty_type='standard',
            start_date=prod.purchase_date,
            expiry_date=prod.purchase_date + timedelta(days=730)
        )
        db.session.add(warr)
        db.session.flush()

        # 4. Create Claim
        clm = Claim(
            user_id=user_id,
            product_id=prod.product_id,
            warranty_id=warr.warranty_id,
            fault_occurrence_date=date.today() - timedelta(days=5),
            fault_description='Display panel backlight sudden failure',
            damage_type='electrical_failure'
        )
        db.session.add(clm)
        db.session.commit()
        print(f"[1] Claim created: {clm.claim_id}")

        # 5. Generate Visual Claim Summary Card
        card_path = generate_claim_summary_card(clm.claim_id)
        print(f"[2] Claim card generated at: {card_path}")

        # 6. Evaluate 14 Business Rules
        rule_res = evaluate_warranty_rules(clm.claim_id)
        print(f"[3] Rules evaluated: {rule_res['passed_count']} passed, {rule_res['failed_count']} failed")

        # 7. Predict ML Tabular Model
        py_pred = predict_claim(clm.claim_id)
        print(f"[4] Python ML predicted: {py_pred['predicted_class']} (Valid conf: {py_pred['confidence_valid']})")

        # 8. Predict GTM Visual Model
        gtm_pred = predict_gtm(clm.claim_id, card_path)
        print(f"[5] GTM Visual predicted: {gtm_pred['predicted_class']} (Valid conf: {gtm_pred['confidence_valid']})")

        # 9. Evaluate Final Decision
        dec = evaluate_final_decision(clm.claim_id, py_pred, gtm_pred, rule_res)
        print(f"[6] Final Decision: {dec['final_decision']} | Status: {dec['claim_status']} | Consistency: {dec['consistency_status']}")

        # 10. Generate Evaluation PDF Report
        pdf_path = generate_claim_pdf_report(clm.claim_id)
        print(f"[7] Evaluation report produced: {pdf_path}")

        print("\n[SUCCESS] Entire service integration pipeline passed flawlessly!")

if __name__ == '__main__':
    run_test()
