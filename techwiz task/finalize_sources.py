from pathlib import Path
p=Path(__file__).parent
s=(p/'01_account_login_product.py').read_text(encoding='utf-8')
a=s.index('def register_demo_user()')
b=s.index('def login(',a)
s=s[:a]+s[b:]
s=s.replace('    register_demo_user()\n','').replace('    print("Demo login: demo@assurex.local / Demo@123")\n','')
s=s.replace('ask("Email", "demo@assurex.local")','ask("Email")').replace('ask("Password", "Demo@123")','ask("Password")')
for label,default in [('Product name','ThinkBook Laptop'),('Category','Laptop'),('Brand','Lenovo'),('Model','ThinkBook 14'),('Serial number','SN-998214A'),('Purchase date (YYYY-MM-DD)','2025-11-15'),('Purchase price','1299'),('Warranty duration in months','24'),('Retailer','BestBuy Retail')]:
    s=s.replace(f'ask("{label}", "{default}")',f'ask("{label}")')
s=s.replace('import argparse','import argparse\nimport os').replace('DATA_DIR = BASE_DIR / "data"','DATA_DIR = Path(os.environ.get("ASSUREX_DATA_DIR", BASE_DIR / "instance"))').replace('assurex_demo.db','assurex.db')
(p/'01_account_login_product.py').write_text(s,encoding='utf-8')
s=(p/'06b_teachable_machine_inference.py').read_text(encoding='utf-8')
a=s.index('    try:\n        import tensorflow as tf',s.index('def main()'))
b=s.index('    Path(args.out).parent.mkdir',a)
s=s[:a]+'''    if not args.labels:
        raise SystemExit("Provide the confirmed label mapping with --labels.")
    result = predict(Path(args.model), Path(args.labels), Path(args.card))
    result["claim_id"] = args.claim_id
    result["source_card"] = args.card

'''+s[b:]
s=s.replace('    if not path or not path.exists():\n        return CLASS_NAMES.copy()', '    if not path or not path.exists():\n        raise ValueError("A confirmed labels file is required.")').replace('return labels or CLASS_NAMES.copy()', 'return labels')
(p/'06b_teachable_machine_inference.py').write_text(s,encoding='utf-8')
(p/'Frontend/navbar.html').write_text('<nav aria-label="Main navigation"><a href="/">AssureX</a> <a href="/claim.html">New claim</a> <a href="/user-profile.html">My claims</a> <a href="/contact.html">Support</a></nav>',encoding='utf-8')
s=(p/'Frontend/assets/js/workbench.js').read_text(encoding='utf-8')
s=s.replace('<div class="actions"><a class="button" href="/user-profile.html">Go to my claims', '<p class="muted" style="font-size:12px;margin-top:20px">${escapeHTML(result.policy_note || "")}</p><div class="actions"><a class="button" href="/user-profile.html">Go to my claims')
(p/'Frontend/assets/js/workbench.js').write_text(s,encoding='utf-8')
