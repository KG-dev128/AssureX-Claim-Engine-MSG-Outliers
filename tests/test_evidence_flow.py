import json
import urllib.request
from datetime import date, timedelta

def req(url, data=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    r = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data is not None else None,
        headers=headers
    )
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

def upload(url, file_bytes, filename, doc_type, claim_id, token):
    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="claim_id"\r\n\r\n{claim_id}\r\n'
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="doc_type"\r\n\r\n{doc_type}\r\n'
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: image/png\r\n\r\n'
    ).encode('utf-8') + file_bytes + f'\r\n--{boundary}--\r\n'.encode('utf-8')

    headers = {
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Authorization': f'Bearer {token}'
    }
    r = urllib.request.Request(url, data=body, headers=headers, method='POST')
    with urllib.request.urlopen(r) as resp:
        return resp.status, json.loads(resp.read().decode())

def run():
    # 1. Login
    st, res = req('http://127.0.0.1:5000/api/auth/login', {'email': 'customer@demo.com', 'password': 'Password123!'})
    tok = res['access_token']
    print('1. Login OK')

    # 2. Register fresh product with active warranty
    today = date.today()
    purchase_date = (today - timedelta(days=60)).isoformat()
    fault_date = (today - timedelta(days=5)).isoformat()

    st, res = req('http://127.0.0.1:5000/api/products/', {
        'product_name': 'Sony WH-1000XM5',
        'category': 'electronics',
        'brand': 'Sony',
        'model_number': 'WH1000XM5',
        'serial_number': f'SN-SONY-778899',
        'purchase_date': purchase_date,
        'purchase_price': 399.99,
        'warranty_duration_months': 12
    }, tok)
    prod = res['product']
    prod_id = prod['product_id']
    print(f"2. Product Registered: {prod['product_name']} ({prod['serial_number']})")

    # 3. Create Draft Claim (fault 5 days ago)
    st, res = req('http://127.0.0.1:5000/api/claims/', {
        'product_id': prod_id,
        'fault_occurrence_date': fault_date,
        'damage_type': 'electrical_failure',
        'fault_description': 'Right ear cup audio cut out and ANC speaker hums loudly.'
    }, tok)
    claim_id = res['claim']['claim_id']
    print(f"3. Draft Claim Created: {claim_id}")

    # 4. Upload all 3 evidence documents
    dummy_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'

    st, _ = upload('http://127.0.0.1:5000/api/documents/upload', dummy_png, 'receipt.png', 'receipt', claim_id, tok)
    print('4a. Uploaded Receipt (Proof of Purchase)')

    st, _ = upload('http://127.0.0.1:5000/api/documents/upload', dummy_png, 'fault_photo.png', 'fault_evidence', claim_id, tok)
    print('4b. Uploaded Fault Evidence (Failure Proof)')

    st, _ = upload('http://127.0.0.1:5000/api/documents/upload', dummy_png, 'serial_label.png', 'product_image', claim_id, tok)
    print('4c. Uploaded Product Label Image')

    # 5. Submit & Evaluate Claim
    st, eval_res = req(f'http://127.0.0.1:5000/api/claims/{claim_id}/submit', {}, tok)
    print('\n=== EVALUATION RESULTS ===')
    print('Decision:', eval_res.get('decision'))
    print('Status:', eval_res.get('status'))
    print('Consistency:', eval_res.get('consistency'))

    print('\n=== 14 BUSINESS RULES VERIFICATION ===')
    for r in eval_res.get('rules', {}).get('results', []):
        mark = '[PASS]' if r['rule_passed'] else '[FAIL]'
        print(f"  {r['rule_name']:<32} {mark}  |  {r['details']}")

if __name__ == '__main__':
    run()
