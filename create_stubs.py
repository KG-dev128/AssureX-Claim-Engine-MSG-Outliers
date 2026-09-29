import os
stubs = {
    'profile': 'profile_bp',
    'products': 'products_bp',
    'warranties': 'warranties_bp',
    'documents': 'documents_bp',
    'claims': 'claims_bp',
    'ml': 'ml_bp',
    'reviews': 'reviews_bp',
    'dashboard': 'dashboard_bp',
    'search': 'search_bp',
    'reports': 'reports_bp',
    'admin': 'admin_bp',
}
for name, bp_var in stubs.items():
    path = os.path.join('app', 'routes', f'{name}.py')
    with open(path, 'w') as f:
        f.write(f'"""app/routes/{name}.py"""\nfrom flask import Blueprint\n{bp_var} = Blueprint("{name}", __name__)\n')
    print(f'Created {path}')
print('All stubs created.')
