"""
tests/test_api_endpoints.py
Comprehensive integration test suite covering all 12 REST API Blueprints.
"""
import sys
import os
import json
import io
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import date, timedelta
from app import create_app
from app.extensions import db
from app.models import User, Product, Warranty, Claim, Document
from app.services.policy_service import seed_default_policies

def run_api_tests():
    app = create_app('testing')
    client = app.test_client()

    with app.app_context():
        db.create_all()
        seed_default_policies()

        print("=== 1. Testing Auth API ===")
        # Register customer
        res = client.post('/api/auth/register', json={
            'username': 'john_doe',
            'email': 'john@example.com',
            'password': 'Password123!',
            'role': 'customer',
            'full_name': 'John Doe',
            'phone': '+123456789'
        })
        assert res.status_code == 201, f"Customer register failed: {res.data}"
        print(" [PASS] Customer registration")

        # Register admin
        res_adm = client.post('/api/auth/register', json={
            'username': 'admin_boss',
            'email': 'admin@assurex.com',
            'password': 'AdminPassword123!',
            'role': 'admin',
            'full_name': 'System Administrator'
        })
        assert res_adm.status_code == 201, f"Admin register failed: {res_adm.data}"
        print(" [PASS] Admin registration")

        # Login customer
        res = client.post('/api/auth/login', json={
            'email': 'john@example.com',
            'password': 'Password123!'
        })
        assert res.status_code == 200, f"Customer login failed: {res.data}"
        customer_token = res.get_json()['access_token']
        customer_headers = {'Authorization': f'Bearer {customer_token}'}
        print(" [PASS] Customer login & JWT generation")

        # Login admin
        res = client.post('/api/auth/login', json={
            'email': 'admin@assurex.com',
            'password': 'AdminPassword123!'
        })
        assert res.status_code == 200
        admin_token = res.get_json()['access_token']
        admin_headers = {'Authorization': f'Bearer {admin_token}'}
        print(" [PASS] Admin login & JWT generation")

        # Auth /me
        res = client.get('/api/auth/me', headers=customer_headers)
        assert res.status_code == 200
        assert res.get_json()['user']['username'] == 'john_doe'
        print(" [PASS] /api/auth/me current user retrieval")

        print("\n=== 2. Testing Profile API ===")
        # Get profile
        res = client.get('/api/profile/', headers=customer_headers)
        assert res.status_code == 200
        assert res.get_json()['profile']['full_name'] == 'John Doe'

        # Update profile
        res = client.put('/api/profile/', headers=customer_headers, json={
            'address': '123 Innovation Drive, Silicon Valley, CA'
        })
        assert res.status_code == 200
        assert res.get_json()['profile']['address'] == '123 Innovation Drive, Silicon Valley, CA'
        print(" [PASS] Profile fetch and update")

        print("\n=== 3. Testing Products API ===")
        # Register product
        p_res = client.post('/api/products/', headers=customer_headers, json={
            'product_name': 'Sony WH-1000XM5',
            'category': 'electronics',
            'brand': 'Sony',
            'model_number': 'WH1000XM5/B',
            'serial_number': 'SN-SONY-778899',
            'purchase_date': str(date.today() - timedelta(days=60)),
            'purchase_price': 399.99,
            'retailer': 'Best Buy',
            'warranty_duration_months': 12
        })
        assert p_res.status_code == 201, f"Product creation failed: {p_res.data}"
        product_id = p_res.get_json()['product']['product_id']
        print(f" [PASS] Product registered: {product_id}")

        # List products
        res = client.get('/api/products/', headers=customer_headers)
        assert res.status_code == 200
        assert res.get_json()['count'] >= 1
        print(" [PASS] List products")

        # Get product detail
        res = client.get(f'/api/products/{product_id}', headers=customer_headers)
        assert res.status_code == 200
        assert res.get_json()['product']['model_number'] == 'WH1000XM5/B'
        print(" [PASS] Get product detail with warranty")

        # Add repair record
        res = client.post(f'/api/products/{product_id}/repairs', headers=customer_headers, json={
            'repair_date': str(date.today() - timedelta(days=20)),
            'repair_center': 'Sony Authorized Service Center',
            'is_authorized': True,
            'replaced_parts': 'Ear cushion assembly',
            'repair_outcome': 'Successful',
            'repair_cost': 45.00
        })
        assert res.status_code == 201
        print(" [PASS] Add product repair record")

        print("\n=== 4. Testing Warranties API ===")
        # Get warranty for product
        res = client.get(f'/api/warranties/product/{product_id}', headers=customer_headers)
        assert res.status_code == 200
        warranties = res.get_json()['warranties']
        assert len(warranties) >= 1
        warranty_id = warranties[0]['warranty_id']
        print(f" [PASS] Fetched auto-generated warranty: {warranty_id}")

        # Check expiring endpoint
        res = client.get('/api/warranties/expiring?days=365', headers=customer_headers)
        assert res.status_code == 200
        print(" [PASS] Checked expiring warranties")

        print("\n=== 5. Testing Documents API ===")
        # Upload mock receipt
        mock_file = (io.BytesIO(b"INVOICE #INV-9988\nDate: 2024-05-10\nSerial No: SN-SONY-778899\nTotal: $399.99"), "receipt.txt")
        res = client.post('/api/documents/upload', headers=customer_headers, data={
            'file': (io.BytesIO(b"Mock invoice data SN-SONY-778899 Total: 399.99"), 'invoice.png'),
            'doc_type': 'receipt',
            'product_id': product_id
        }, content_type='multipart/form-data')
        assert res.status_code == 201, f"Doc upload failed: {res.data}"
        doc_id = res.get_json()['document']['doc_id']
        print(f" [PASS] Uploaded document with SHA-256 hash: {doc_id}")

        print("\n=== 6. Testing Claims API ===")
        # Create claim
        res = client.post('/api/claims/', headers=customer_headers, json={
            'product_id': product_id,
            'fault_occurrence_date': str(date.today() - timedelta(days=3)),
            'fault_description': 'Active noise cancellation stopped functioning on left earcup',
            'damage_type': 'electrical_failure'
        })
        assert res.status_code == 201, f"Claim creation failed: {res.data}"
        claim_id = res.get_json()['claim']['claim_id']
        print(f" [PASS] Draft claim created: {claim_id}")

        # Associate document with claim
        doc = Document.query.get(doc_id)
        doc.claim_id = claim_id
        db.session.commit()

        # Submit claim & trigger automated evaluation
        res = client.post(f'/api/claims/{claim_id}/submit', headers=customer_headers)
        assert res.status_code == 200, f"Submit claim failed: {res.data}"
        eval_data = res.get_json()
        print(f" [PASS] Automated evaluation returned final decision: {eval_data['decision']} (Status: {eval_data['status']})")

        # Claim visual card endpoint
        res = client.get(f'/api/claims/{claim_id}/card', headers=customer_headers)
        assert res.status_code == 200
        print(" [PASS] Generated Claim Summary Card image endpoint")

        # Claim rules breakdown endpoint
        res = client.get(f'/api/claims/{claim_id}/rules', headers=customer_headers)
        assert res.status_code == 200
        print(" [PASS] 14-Rule verification breakdown endpoint")

        # Claim decision endpoint
        res = client.get(f'/api/claims/{claim_id}/decision', headers=customer_headers)
        assert res.status_code == 200
        print(" [PASS] Claim decision record endpoint")

        print("\n=== 7. Testing ML & GTM API ===")
        res = client.post(f'/api/ml/predict-python/{claim_id}', headers=customer_headers)
        assert res.status_code == 200
        print(" [PASS] Explicit Python ML prediction endpoint")

        res = client.post(f'/api/ml/predict-gtm/{claim_id}', headers=customer_headers)
        assert res.status_code == 200
        print(" [PASS] Explicit GTM visual prediction endpoint")

        res = client.get('/api/ml/versions', headers=customer_headers)
        assert res.status_code == 200
        print(" [PASS] Model versions registry endpoint")

        print("\n=== 8. Testing Reviews API ===")
        # Queue view
        res = client.get('/api/reviews/queue', headers=admin_headers)
        assert res.status_code == 200
        print(f" [PASS] Reviewer queue returned {res.get_json()['queue_count']} item(s)")

        # Reviewer action
        res = client.post(f'/api/reviews/{claim_id}/action', headers=admin_headers, json={
            'action_type': 'approve',
            'comments': 'Verified receipt and serial match. Claim approved.'
        })
        assert res.status_code == 200
        assert res.get_json()['new_status'] == 'approved'
        print(" [PASS] Reviewer action approval applied")

        print("\n=== 9. Testing Dashboard API ===")
        # Customer stats
        res = client.get('/api/dashboard/stats', headers=customer_headers)
        assert res.status_code == 200
        # Admin stats
        res_adm = client.get('/api/dashboard/stats', headers=admin_headers)
        assert res_adm.status_code == 200
        print(" [PASS] Dashboard stats for customer and admin")

        # Recent activity
        res = client.get('/api/dashboard/recent', headers=admin_headers)
        assert res.status_code == 200
        print(" [PASS] Dashboard recent activity feed")

        print("\n=== 10. Testing Search API ===")
        res = client.get('/api/search/claims?q=noise', headers=customer_headers)
        assert res.status_code == 200
        assert res.get_json()['count'] >= 1
        print(" [PASS] Full-text claim search")

        res = client.get('/api/search/products?q=Sony', headers=customer_headers)
        assert res.status_code == 200
        assert res.get_json()['count'] >= 1
        print(" [PASS] Product search")

        print("\n=== 11. Testing Reports API ===")
        res = client.get(f'/api/reports/claim/{claim_id}/pdf', headers=customer_headers)
        if res.status_code != 200:
            print("PDF error:", res.status_code, res.data)
        assert res.status_code == 200
        assert res.headers['Content-Type'] in ['application/pdf', 'text/plain']
        print(" [PASS] PDF report download endpoint")

        res = client.get('/api/reports/claims/csv', headers=customer_headers)
        assert res.status_code == 200
        assert 'claim_id' in res.data.decode('utf-8')
        print(" [PASS] CSV claims dataset export endpoint")

        print("\n=== 12. Testing Admin API ===")
        res = client.get('/api/admin/users', headers=admin_headers)
        assert res.status_code == 200
        print(" [PASS] Admin users listing")

        res = client.get('/api/admin/audit', headers=admin_headers)
        assert res.status_code == 200
        print(" [PASS] Admin audit trail inspection")

        res = client.get('/api/admin/policies', headers=admin_headers)
        assert res.status_code == 200
        print(" [PASS] Admin warranty policies inspection")

        print("\n" + "="*50)
        print("ALL 12 API BLUEPRINTS VERIFIED AND PASSING!")
        print("="*50)

if __name__ == '__main__':
    run_api_tests()
