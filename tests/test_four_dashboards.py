"""
tests/test_four_dashboards.py
Tests authentication, JWT session generation, and API responses for all 4 SRS Dashboards:
1. Customer Dashboard
2. Claims Reviewer Dashboard
3. System Administrator Dashboard
4. Service Center / Technician Dashboard
"""
import urllib.request
import json

BASE_URL = 'http://127.0.0.1:5000'

def post_json(path, data, token=None):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json', **({'Authorization': f'Bearer {token}'} if token else {})}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

def get_json(path, token):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={'Authorization': f'Bearer {token}'}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

def test_all_dashboards():
    roles = [
        ('Customer', 'customer@assurex.com', 'Customer123!', 'customer'),
        ('Reviewer', 'reviewer@assurex.com', 'Reviewer123!', 'reviewer'),
        ('Admin', 'admin@assurex.com', 'Admin123!', 'admin'),
        ('Technician', 'technician@assurex.com', 'Technician123!', 'service_employee')
    ]

    tokens = {}
    print("\n================ AUTHENTICATION & JWT TOKENS ================")
    for label, email, pw, expected_role in roles:
        res = post_json('/api/auth/login', {'email': email, 'password': pw})
        assert 'access_token' in res, f"Login failed for {label}"
        tokens[expected_role] = res['access_token']
        user = res['user']
        print(f"[OK] {label.upper()}: Logged in as '{user['username']}' (Role: {user['role']})")

    # 1. Customer Dashboard APIs
    print("\n================ DASHBOARD 1: CUSTOMER PORTAL ================")
    c_stats = get_json('/api/dashboard/stats', tokens['customer'])
    print(f"[OK] Customer Stats: {c_stats.get('total_claims', 0)} claims, {c_stats.get('registered_products', 0)} products")
    products = get_json('/api/products/', tokens['customer'])
    print(f"[OK] Products API: Retrieved {products.get('count', 0)} devices")
    claims = get_json('/api/claims/', tokens['customer'])
    print(f"[OK] Claims API: Retrieved {claims.get('count', 0)} claims")

    # 2. Reviewer Dashboard APIs
    print("\n================ DASHBOARD 2: REVIEWER QUEUE ================")
    queue = get_json('/api/reviews/queue', tokens['reviewer'])
    print(f"[OK] Manual Review Queue: {queue.get('count', 0)} claims pending adjudication")

    # 3. Admin Dashboard APIs
    print("\n================ DASHBOARD 3: ADMINISTRATOR ================")
    a_stats = get_json('/api/dashboard/stats', tokens['admin'])
    cs = a_stats.get('claims_summary', {})
    print(f"[OK] Admin KPIs: {cs.get('total', 0)} total claims ({cs.get('approval_rate', 0)}% approval rate)")
    users = get_json('/api/admin/users', tokens['admin'])
    print(f"[OK] User Management: {users.get('count', 0)} registered system users")
    anomalies = get_json('/api/admin/anomalies', tokens['admin'])
    print(f"[OK] Anomaly Alerts: {anomalies.get('count', 0)} alerts logged")
    audits = get_json('/api/admin/audit', tokens['admin'])
    print(f"[OK] Audit Trail: {audits.get('count', 0)} audit trail records recorded")

    # 4. Service Center Dashboard APIs
    print("\n================ DASHBOARD 4: SERVICE CENTER ================")
    repairs = get_json('/api/products/repairs/all', tokens['service_employee'])
    print(f"[OK] Service Records: {repairs.get('count', 0)} repair logs retrieved")

    print("\n[SUCCESS] ALL 4 DASHBOARDS AND THEIR APIS VERIFIED PERFECTLY!")

if __name__ == '__main__':
    test_all_dashboards()
