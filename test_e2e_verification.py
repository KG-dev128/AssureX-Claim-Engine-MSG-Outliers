"""
test_e2e_verification.py
End-to-End Verification using Python Standard Library (urllib)
Verifies:
1. Public tracking (/api/search/track)
2. Admin authentication (/api/auth/login)
3. Customer registration & login
4. RBAC: Customers forbidden from /api/reviews/queue & /api/admin/users (403)
5. Product registration
6. IDOR Prevention: Customer B cannot claim Customer A's product (403)
7. Customer claim creation & automated evaluation
8. IDOR Prevention: Customer B cannot view Customer A's claim, rules, card, or PDF (403)
9. Customer A can view own claim & rules
10. Admin role assignment (Customer B -> Reviewer)
11. Reviewer accessing queue & adjudicating claim
12. Real-time public tracking by Claim ID
13. Role-based dashboard stats isolation
"""
import urllib.request
import urllib.parse
import urllib.error
import json
import sys

BASE_URL = "http://127.0.0.1:5000"

def http_req(url, method="GET", data=None, headers=None):
    if headers is None:
        headers = {}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            status = resp.status
            try:
                parsed = json.loads(content)
            except Exception:
                parsed = content
            return status, parsed
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8")
        try:
            parsed = json.loads(content)
        except Exception:
            parsed = content
        return e.code, parsed

def run_tests():
    print("=" * 70)
    print("ASSUREX FULL-STACK E2E VERIFICATION SUITE")
    print("=" * 70)

    # 1. Public Tracking
    print("\n[1] Testing Public Tracking with non-existent query...")
    status, data = http_req(f"{BASE_URL}/api/search/track?q=CLM-NONEXISTENT")
    print(f"  Status: {status} (Expected 404)")
    assert status == 404, f"Expected 404, got {status}"

    # 2. Admin Authentication
    print("\n[2] Testing Admin Authentication...")
    status, admin_data = http_req(f"{BASE_URL}/api/auth/login", method="POST", data={
        "email": "admin@assurex.com",
        "password": "Admin123!"
    })
    print(f"  Admin login status: {status}")
    assert status == 200, f"Admin login failed: {admin_data}"
    admin_token = admin_data["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print(f"  Admin authenticated: role = {admin_data['user']['role']}")

    # 3. Customer A Registration & Login
    print("\n[3] Testing Customer A Registration / Login...")
    cust_a_email = "test_user_a@example.com"
    status, cust_a_login = http_req(f"{BASE_URL}/api/auth/login", method="POST", data={
        "email": cust_a_email,
        "password": "Password123!"
    })
    if status != 200:
        status, _ = http_req(f"{BASE_URL}/api/auth/register", method="POST", data={
            "username": "test_user_a",
            "email": cust_a_email,
            "password": "Password123!",
            "full_name": "Test Customer A"
        })
        status, cust_a_login = http_req(f"{BASE_URL}/api/auth/login", method="POST", data={
            "email": cust_a_email,
            "password": "Password123!"
        })

    assert status == 200, "Customer A login failed"
    token_a = cust_a_login["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}
    print("  Customer A authenticated successfully.")

    # 4. Customer B Registration & Login
    print("\n[4] Testing Customer B Registration / Login...")
    cust_b_email = "test_user_b@example.com"
    status, cust_b_login = http_req(f"{BASE_URL}/api/auth/login", method="POST", data={
        "email": cust_b_email,
        "password": "Password123!"
    })
    if status != 200:
        http_req(f"{BASE_URL}/api/auth/register", method="POST", data={
            "username": "test_user_b",
            "email": cust_b_email,
            "password": "Password123!",
            "full_name": "Test Customer B"
        })
        status, cust_b_login = http_req(f"{BASE_URL}/api/auth/login", method="POST", data={
            "email": cust_b_email,
            "password": "Password123!"
        })

    assert status == 200, "Customer B login failed"
    token_b = cust_b_login["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}
    print("  Customer B authenticated successfully.")

    # 5. RBAC: Customer A forbidden on Reviewer & Admin endpoints
    print("\n[5] Testing RBAC on Restricted Routes...")
    status, _ = http_req(f"{BASE_URL}/api/reviews/queue", headers=headers_a)
    print(f"  Customer accessing /api/reviews/queue: {status} (Expected 403)")
    assert status == 403, f"Expected 403, got {status}"

    status, _ = http_req(f"{BASE_URL}/api/admin/users", headers=headers_a)
    print(f"  Customer accessing /api/admin/users: {status} (Expected 403)")
    assert status == 403, f"Expected 403, got {status}"

    # 6. Customer A registers a product
    print("\n[6] Customer A registering equipment...")
    status, prod_res = http_req(f"{BASE_URL}/api/products/", method="POST", headers=headers_a, data={
        "product_name": "ThinkPad P16 Extreme Workstation",
        "category": "electronics",
        "brand": "Lenovo",
        "model_number": "21FA001SUS",
        "serial_number": "SN-P16-887766",
        "purchase_date": "2026-02-01",
        "warranty_duration_months": 36,
        "retailer": "Direct Enterprise"
    })
    print(f"  Product registration: {status}")
    assert status in [200, 201], f"Product registration failed: {prod_res}"
    product_id_a = prod_res["product"]["product_id"]
    print(f"  Product ID: {product_id_a}")

    # 7. IDOR Check: Customer B tries to file a claim against Customer A's product
    print("\n[7] Testing IDOR Prevention on Claim Creation...")
    status, idor_res = http_req(f"{BASE_URL}/api/claims/", method="POST", headers=headers_b, data={
        "product_id": product_id_a,
        "damage_type": "electrical_failure",
        "fault_date": "2026-03-01",
        "fault_description": "Unauthorized claim injection on another user product"
    })
    print(f"  Customer B filing claim on Customer A's product: {status} (Expected 403)")
    assert status == 403, f"Expected 403 Forbidden, got {status}"

    # 8. Customer A files legitimate claim with auto-evaluation
    print("\n[8] Customer A filing valid claim with auto-evaluation...")
    status, claim_res = http_req(f"{BASE_URL}/api/claims/", method="POST", headers=headers_a, data={
        "product_id": product_id_a,
        "damage_type": "electrical_failure",
        "fault_date": "2026-03-01",
        "fault_description": "Motherboard power stage capacitor exploded during operation",
        "auto_evaluate": True
    })
    print(f"  Claim creation & evaluation status: {status}")
    assert status in [200, 201], f"Claim submission failed: {claim_res}"
    claim_id = claim_res.get("claim_id") or claim_res["claim"]["claim_id"]
    print(f"  Claim filed successfully! Claim ID: {claim_id}")

    # 9. IDOR Check: Customer B cannot inspect Customer A's claim, rules, card, or PDF
    print("\n[9] Testing IDOR Prevention on Claim Inspection & Downloads...")
    status, _ = http_req(f"{BASE_URL}/api/claims/{claim_id}", headers=headers_b)
    print(f"  Customer B accessing Customer A's claim: {status} (Expected 403)")
    assert status == 403

    status, _ = http_req(f"{BASE_URL}/api/claims/{claim_id}/rules", headers=headers_b)
    print(f"  Customer B accessing Customer A's rules: {status} (Expected 403)")
    assert status == 403

    status, _ = http_req(f"{BASE_URL}/api/claims/{claim_id}/card", headers=headers_b)
    print(f"  Customer B downloading Customer A's card: {status} (Expected 403)")
    assert status == 403

    status, _ = http_req(f"{BASE_URL}/api/reports/claim/{claim_id}/pdf", headers=headers_b)
    print(f"  Customer B downloading Customer A's report PDF: {status} (Expected 403)")
    assert status == 403

    # 10. Customer A CAN inspect their own claim and rules
    print("\n[10] Customer A accessing own claim & rules...")
    status, own_claim = http_req(f"{BASE_URL}/api/claims/{claim_id}", headers=headers_a)
    assert status == 200, "Customer A could not access own claim"
    status, own_rules = http_req(f"{BASE_URL}/api/claims/{claim_id}/rules", headers=headers_a)
    assert status == 200, "Customer A could not access own rules"
    print("  Customer A verified own claim details and 14-rule matrix.")

    # 11. Admin promotes Customer B to Reviewer
    print("\n[11] Admin promoting User B to Reviewer & Testing Adjudication...")
    user_b_id = cust_b_login["user"]["user_id"]
    status, _ = http_req(f"{BASE_URL}/api/admin/users/{user_b_id}/role", method="PUT", headers=admin_headers, data={
        "role": "reviewer"
    })
    assert status == 200

    # User B logs in to get new reviewer token
    status, rev_login = http_req(f"{BASE_URL}/api/auth/login", method="POST", data={
        "email": cust_b_email,
        "password": "Password123!"
    })
    token_rev = rev_login["access_token"]
    headers_rev = {"Authorization": f"Bearer {token_rev}"}

    # Reviewer accesses queue
    status, queue_res = http_req(f"{BASE_URL}/api/reviews/queue", headers=headers_rev)
    print(f"  Reviewer accessing queue: {status} (Expected 200)")
    assert status == 200
    claims_in_queue = queue_res.get("claims", [])
    print(f"  Queue items count: {len(claims_in_queue)}")

    # Reviewer adjudicates the claim
    status, adj_res = http_req(f"{BASE_URL}/api/reviews/{claim_id}/action", method="POST", headers=headers_rev, data={
        "action_type": "approve",
        "comments": "Defect confirmed under standard manufacturer warranty terms"
    })
    print(f"  Reviewer adjudication: {status} (Expected 200)")
    assert status == 200
    print(f"  New claim status: {adj_res.get('new_status')}")

    # 12. Public Tracking with real Claim ID
    print("\n[12] Public Tracking with verified Claim ID...")
    status, track_res = http_req(f"{BASE_URL}/api/search/track?q={claim_id}")
    print(f"  Public track real claim: {status} (Expected 200)")
    assert status == 200
    print(f"  Status returned: {track_res['claim']['status']}")

    # 13. Dashboard Isolation
    print("\n[13] Testing Role-Based Dashboard Isolation...")
    status, cust_stats = http_req(f"{BASE_URL}/api/dashboard/stats", headers=headers_a)
    assert status == 200 and cust_stats["role"] == "customer"
    print(f"  Customer dashboard: registered_products = {cust_stats['registered_products']}")

    status, admin_stats = http_req(f"{BASE_URL}/api/dashboard/stats", headers=admin_headers)
    assert status == 200 and admin_stats["role"] == "admin"
    print(f"  Admin dashboard: total_claims = {admin_stats['stats']['total_claims']}")

    print("\n" + "=" * 70)
    print("ALL 13 E2E VERIFICATION TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
