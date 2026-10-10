"""
Live End-to-End Verification of ClaimSure_AI / AssureX
Performs real HTTP requests against the live running server at http://127.0.0.1:5000
"""

import json
import urllib.request
import urllib.parse
import urllib.error
import mimetypes

BASE_URL = "http://127.0.0.1:5000"

def get(path):
    url = BASE_URL + path
    req = urllib.request.Request(url, headers={"User-Agent": "VerificationClient/1.0"})
    try:
        with urllib.request.urlopen(req) as res:
            data = res.read()
            return res.status, res.headers, data
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()

def post_json(path, payload):
    url = BASE_URL + path
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "VerificationClient/1.0"}
    )
    try:
        with urllib.request.urlopen(req) as res:
            data = res.read()
            return res.status, res.headers, json.loads(data.decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.headers, json.loads(e.read().decode("utf-8"))

def post_multipart(path, fields, files):
    boundary = "----WebKitFormBoundaryVerification7MA4YWxkTrZu0gW"
    body_parts = []
    
    for k, v in fields.items():
        body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode("utf-8"))
        
    for k, (filename, content) in files.items():
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        header = f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{filename}\"\r\nContent-Type: {mime}\r\n\r\n"
        body_parts.append(header.encode("utf-8") + content + b"\r\n")
        
    body_parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    payload = b"".join(body_parts)
    
    req = urllib.request.Request(
        BASE_URL + path,
        data=payload,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "VerificationClient/1.0"
        }
    )
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, res.headers, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.headers, json.loads(e.read().decode("utf-8"))

print("=" * 70)
print("RUNNING LIVE HTTP VERIFICATION AGAINST http://127.0.0.1:5000")
print("=" * 70)

# 1. Page Routes
print("\n[1/5] Verifying all Frontend HTML Page Routes...")
pages = [
    "/",
    "/index.html",
    "/login.html",
    "/register.html",
    "/claim.html",
    "/user-profile.html",
    "/reviewer.html",
    "/service-center-dashboard.html",
    "/contact.html",
    "/navbar.html",
]
for page in pages:
    status, headers, content = get(page)
    cors = headers.get("Access-Control-Allow-Origin")
    assert status == 200, f"Page {page} failed with status {status}"
    assert len(content) > 500, f"Page {page} content was empty or too small"
    print(f"  [PASS] {page.ljust(35)} -> HTTP {status} (Length: {len(content)} bytes, CORS: {cors})")

# 2. Static Asset Routes
print("\n[2/5] Verifying Static Assets (CSS, JS, Media)...")
assets = [
    "/assets/css/root.css",
    "/assets/css/style.css",
    "/assets/js/main.js",
    "/assets/media/header.png",
    "/assets/media/demo1.mp4",
    "/assets/media/demo2.mp4",
    "/assets/media/demo3.mp4",
]
for asset in assets:
    status, headers, content = get(asset)
    assert status == 200, f"Asset {asset} failed with status {status}"
    print(f"  [PASS] {asset.ljust(35)} -> HTTP {status} ({len(content)} bytes)")

# 3. Authentication & Account APIs
print("\n[3/5] Verifying Authentication & User APIs...")
# Login Success
status, _, res = post_json("/api/login", {"email": "demo@assurex.local", "password": "Demo@123"})
assert status == 200 and res["success"] is True, f"Login failed: {res}"
print(f"  [PASS] POST /api/login (valid)          -> HTTP {status} (User: {res['user']['name']})")

# Login Invalid
status, _, res = post_json("/api/login", {"email": "invalid@assurex.local", "password": "WrongPassword"})
assert status == 401 and res["success"] is False, f"Expected 401: {res}"
print(f"  [PASS] POST /api/login (invalid creds)  -> HTTP {status} (Error caught gracefully)")

# User Session
status, _, res = get("/api/user")
user_json = json.loads(res.decode("utf-8"))
assert status == 200 and user_json["success"] is True
print(f"  [PASS] GET /api/user                    -> HTTP {status} (User ID: {user_json['user']['user_id']})")

# Products List
status, _, res = get("/api/products")
prod_json = json.loads(res.decode("utf-8"))
assert status == 200 and prod_json["success"] is True
print(f"  [PASS] GET /api/products                -> HTTP {status} ({len(prod_json['products'])} products available)")

# 4. End-to-End Claim Intake, Extraction & Dual-AI Evaluation Flow
print("\n[4/5] Verifying Complete End-to-End Claim Lifecycle...")
with open("Frontend/assets/media/header.png", "rb") as f:
    sample_img = f.read()

# Intake & Document Fingerprinting (Step 2, 3, 4)
intake_fields = {
    "category": "Smartphone",
    "claim_title": "Screen Flickering & Battery Drain",
    "purchase_date": "2024-05-10",
    "issue_description": "Display flickers erratically when battery is below 40%."
}
intake_files = {
    "receipt": ("purchase_invoice.png", sample_img),
    "warranty": ("warranty_card.png", sample_img),
    "damage": ("screen_defect.png", sample_img),
}
status, headers, intake_res = post_multipart("/api/claim/process", intake_fields, intake_files)
assert status == 200 and intake_res["success"] is True, f"Intake failed: {intake_res}"
claim_id = intake_res["claim_id"]
fps = intake_res["fingerprints"]
ocr_data = intake_res["extracted_fields"]
print(f"  [PASS] POST /api/claim/process          -> HTTP {status}")
print(f"     Claim ID: {claim_id}")
print(f"     Document Fingerprints: {len(fps)} computed")
for fp in fps:
    print(f"       - {fp['document_type']}: SHA-256 = {fp['sha256'][:16]}...")
print(f"     Extracted OCR Fields:")
print(f"       - Invoice #: {ocr_data['invoice_number']}")
print(f"       - Serial #:  {ocr_data['serial_number']}")
print(f"       - Store:     {ocr_data['store_name']}")
print(f"       - Date:      {ocr_data['purchase_date']}")
print(f"       - Amount:    {ocr_data['paid_amount']}")

# Evaluation with AI & Rules (Step 5 - 10)
eval_payload = {
    "claim_id": claim_id,
    "category": "Smartphone",
    "invoice_number": ocr_data["invoice_number"],
    "store_name": ocr_data["store_name"],
    "serial_number": ocr_data["serial_number"],
    "purchase_date": ocr_data["purchase_date"],
    "paid_amount": ocr_data["paid_amount"],
    "issue_description": "Display flickers erratically when battery is below 40%."
}
status, _, eval_res = post_json("/api/claim/evaluate", eval_payload)
assert status == 200 and eval_res["success"] is True, f"Evaluation failed: {eval_res}"
print(f"  [PASS] POST /api/claim/evaluate         -> HTTP {status}")
print(f"     Automated Decision: {eval_res['decision']} (Type: {eval_res['status_type']})")
print(f"     Model Confidence:   {eval_res['confidence_percent']}")
print(f"     Warranty Status:    {eval_res['rule_status']}")
print(f"     Explanation:        {eval_res['explanation']}")
print(f"     Audit Hash:         {eval_res['audit_hash'][:16]}...")

# Certificate Download (Step 10 PDF)
status, headers, pdf_bytes = get(f"/api/claim/{claim_id}/certificate")
assert status == 200, f"Certificate download failed: {status}"
assert headers.get("Content-Type") == "application/pdf"
assert len(pdf_bytes) > 1000
print(f"  [PASS] GET /api/claim/{claim_id}/certificate -> HTTP {status} (Branded PDF Audit Certificate: {len(pdf_bytes)} bytes)")

# 5. Reviewer & Operations Portals
print("\n[5/5] Verifying Reviewer, Profile & Service Ops APIs...")
# Reviewer Claims Queue
status, _, rev_data = get("/api/reviewer/claims")
rev_claims = json.loads(rev_data.decode("utf-8"))
assert status == 200 and rev_claims["success"] is True
print(f"  [PASS] GET /api/reviewer/claims         -> HTTP {status} ({len(rev_claims['claims'])} claims in queue)")

# Reviewer Adjudication & Audit Lock
review_payload = {
    "claim_id": claim_id,
    "decision": "approve",
    "reason": "Verified purchase receipt and digital warranty card matches Samsung smartphone policy.",
    "reviewer": "Adjudicator Emily"
}
status, _, dec_res = post_json("/api/reviewer/decision", review_payload)
assert status == 200 and dec_res["success"] is True
print(f"  [PASS] POST /api/reviewer/decision      -> HTTP {status} (Audit locked with hash: {dec_res['record_hash'][:16]}...)")

# Customer Profile Claims List
status, _, prof_data = get("/api/claims")
prof_claims = json.loads(prof_data.decode("utf-8"))
assert status == 200 and prof_claims["success"] is True
print(f"  [PASS] GET /api/claims                  -> HTTP {status} ({len(prof_claims['claims'])} claims returned)")

# Service Center Work Orders
status, _, sc_data = get("/api/service-center/claims")
sc_claims = json.loads(sc_data.decode("utf-8"))
assert status == 200 and sc_claims["success"] is True
print(f"  [PASS] GET /api/service-center/claims   -> HTTP {status} ({len(sc_claims['claims'])} active work orders)")

# Contact Form
status, _, contact_res = post_json("/api/contact", {"name": "Test Customer", "message": "Inquiry test"})
assert status == 200 and contact_res["success"] is True
print(f"  [PASS] POST /api/contact                -> HTTP {status} (Message acknowledged)")

print("\n" + "=" * 70)
print("FINAL RESULT: ALL LIVE HTTP VERIFICATION TESTS PASSED SUCCESSFULLY!")
print("=" * 70)
