"""
app/routes/products.py
Product registration, catalog, and repair history management (FR iii, xiii).
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.extensions import db
from app.models import Product, RepairHistory, Warranty
from app.utils.validators import validate_product_payload
from app.utils.date_utils import parse_date_flexible
from app.services.audit_service import log_action
from app.services.auth_service import role_required

products_bp = Blueprint('products', __name__)



@products_bp.route('/', methods=['POST'])
@jwt_required()
def register_product():
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    valid, errors = validate_product_payload(data)
    if not valid:
        return jsonify({'errors': errors}), 400

    try:
        purchase_date = parse_date_flexible(str(data['purchase_date']))
    except Exception as e:
        return jsonify({'error': f"Invalid purchase date: {e}"}), 400

    product = Product(
        user_id=user_id,
        product_name=data['product_name'].strip(),
        category=data['category'].strip().lower(),
        brand=data['brand'].strip(),
        model_number=data['model_number'].strip(),
        serial_number=data['serial_number'].strip(),
        purchase_date=purchase_date,
        purchase_price=float(data.get('purchase_price', 0.0)) if data.get('purchase_price') else None,
        retailer=data.get('retailer'),
        warranty_duration_months=int(data.get('warranty_duration_months', 12)),
    )
    db.session.add(product)
    db.session.flush()

    # Automatically create default standard warranty for the product
    from datetime import timedelta
    warranty_days = product.warranty_duration_months * 30
    expiry_date = product.purchase_date + timedelta(days=warranty_days)
    warranty = Warranty(
        product_id=product.product_id,
        warranty_type='standard',
        start_date=product.purchase_date,
        expiry_date=expiry_date,
        alert_days_before=30,
    )
    db.session.add(warranty)
    db.session.commit()

    log_action(
        user_id=user_id,
        action_type='product_registered',
        entity_type='product',
        entity_id=product.product_id,
        details={'name': product.product_name, 'serial': product.serial_number},
        ip_address=request.remote_addr,
    )

    return jsonify({
        'message': 'Product registered successfully.',
        'product': product.to_dict(),
        'warranty': warranty.to_dict(),
    }), 201


@products_bp.route('/', methods=['GET'])
@jwt_required()
def list_products():
    user_id = get_jwt_identity()
    claims = get_jwt()
    role = claims.get('role', 'customer')

    # Admins, reviewers, and service technicians can view all products or filter by user_id
    filter_user = request.args.get('user_id')
    if role in ['admin', 'reviewer', 'service_employee'] and filter_user:
        products = Product.query.filter_by(user_id=filter_user).all()
    elif role in ['admin', 'reviewer', 'service_employee'] and not filter_user:
        products = Product.query.all()
    else:
        products = Product.query.filter_by(user_id=user_id).all()

    return jsonify({
        'count': len(products),
        'products': [p.to_dict() for p in products]
    }), 200


@products_bp.route('/<product_id>', methods=['GET'])
@jwt_required()
def get_product(product_id):
    user_id = get_jwt_identity()
    claims = get_jwt()
    role = claims.get('role', 'customer')

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found.'}), 404

    if role == 'customer' and product.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    warranties = [w.to_dict() for w in product.warranties.all()]
    repairs = [r.to_dict() for r in product.repairs.all()]
    documents = [d.to_dict() for d in Document.query.filter_by(product_id=product_id).all()]

    data = product.to_dict()
    data['warranties'] = warranties
    data['repairs'] = repairs
    data['documents'] = documents
    return jsonify({'product': data}), 200



@products_bp.route('/<product_id>', methods=['PUT'])
@jwt_required()
def update_product(product_id):
    user_id = get_jwt_identity()
    claims = get_jwt()
    role = claims.get('role', 'customer')

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found.'}), 404

    if role == 'customer' and product.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    data = request.get_json() or {}
    for f in ['product_name', 'category', 'brand', 'model_number', 'serial_number', 'retailer']:
        if f in data:
            setattr(product, f, data[f])

    if 'purchase_price' in data:
        product.purchase_price = float(data['purchase_price'])

    db.session.commit()
    return jsonify({'message': 'Product updated.', 'product': product.to_dict()}), 200


@products_bp.route('/<product_id>', methods=['DELETE'])
@jwt_required()
def delete_product(product_id):
    user_id = get_jwt_identity()
    claims = get_jwt()
    role = claims.get('role', 'customer')

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found.'}), 404

    if role != 'admin' and product.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    db.session.delete(product)
    db.session.commit()
    return jsonify({'message': 'Product deleted.'}), 200


# ── Repair History Sub-resource (FR xiii) ────────────────────────────────────

@products_bp.route('/repairs/all', methods=['GET'])
@role_required('admin', 'reviewer', 'service_employee')
def list_all_repairs():
    repairs = RepairHistory.query.order_by(RepairHistory.repair_date.desc()).limit(100).all()
    results = []
    for r in repairs:
        r_dict = r.to_dict()
        p = Product.query.get(r.product_id)
        r_dict['product_name'] = p.product_name if p else 'Unknown'
        r_dict['serial_number'] = p.serial_number if p else 'Unknown'
        results.append(r_dict)
    return jsonify({'count': len(results), 'repairs': results}), 200


@products_bp.route('/<product_id>/repairs', methods=['GET'])
@jwt_required()
def get_repair_history(product_id):
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found.'}), 404

    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and product.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    repairs = RepairHistory.query.filter_by(product_id=product_id).order_by(RepairHistory.repair_date.desc()).all()
    return jsonify({'product_id': product_id, 'repairs': [r.to_dict() for r in repairs]}), 200


@products_bp.route('/<product_id>/repairs', methods=['POST'])
@jwt_required()
def add_repair_record(product_id):
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found.'}), 404

    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and product.user_id != user_id:
        return jsonify({'error': 'Forbidden: You do not own this product.'}), 403

    data = request.get_json() or {}
    if not data.get('repair_date'):
        return jsonify({'error': 'Repair date is required.'}), 400

    try:
        rdate = parse_date_flexible(str(data['repair_date']))
    except Exception:
        return jsonify({'error': 'Invalid repair date format.'}), 400

    repair = RepairHistory(
        product_id=product_id,
        claim_id=data.get('claim_id'),
        repair_date=rdate,
        repair_center=data.get('repair_center', 'Service Center'),
        is_authorized=bool(data.get('is_authorized', True)),
        replaced_parts=data.get('replaced_parts'),
        repair_outcome=data.get('repair_outcome', 'Successful'),
        repair_cost=float(data.get('repair_cost', 0.0)) if data.get('repair_cost') else None,
        notes=data.get('notes'),
    )
    db.session.add(repair)
    db.session.commit()

    return jsonify({'message': 'Repair history record added.', 'repair': repair.to_dict()}), 201


@products_bp.route('/<product_id>/generate-artifacts', methods=['POST'])
@jwt_required()
def generate_product_artifacts(product_id):
    """
    Admin and authorized users can generate official receipts, warranty cards,
    and defect evidence matching the product category's policy.
    """
    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found.'}), 404

    if role == 'customer' and product.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    from app.services.document_artifact_generator import generate_policy_artifacts_for_product
    options = request.get_json() or {}
    try:
        result = generate_policy_artifacts_for_product(product_id, admin_user_id=user_id, options=options)
        return jsonify({
            'message': f"Generated {result['count']} policy artifacts (Receipt, Warranty Card, Defect Evidence) for {result['product_name']}.",
            'result': result
        }), 201
    except Exception as e:
        return jsonify({'error': f"Failed to generate artifacts: {e}"}), 500

