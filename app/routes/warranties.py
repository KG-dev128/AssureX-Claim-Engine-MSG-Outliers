"""
app/routes/warranties.py
Warranty lifecycle and expiry monitoring endpoints (FR iv, viii, ix).
"""
from datetime import date, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.extensions import db
from app.models import Warranty, Product
from app.utils.date_utils import parse_date_flexible
from app.services.notification_service import check_warranty_expiry_alerts
from app.services.audit_service import log_action
from app.services.auth_service import role_required

warranties_bp = Blueprint('warranties', __name__)


@warranties_bp.route('/', methods=['GET'])
@jwt_required()
def list_warranties():
    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    status_filter = request.args.get('status')

    query = Warranty.query.join(Product)
    if role == 'customer':
        query = query.filter(Product.user_id == user_id)

    today = date.today()
    warranties = query.order_by(Warranty.expiry_date.asc()).all()
    results = []

    for w in warranties:
        w_dict = w.to_dict()
        p = Product.query.get(w.product_id)
        w_dict['product'] = p.to_dict() if p else None
        
        # Calculate derived status
        remaining_days = (w.expiry_date - today).days
        w_dict['remaining_days'] = remaining_days
        if remaining_days < 0:
            w_status = 'expired'
        elif remaining_days <= (w.alert_days_before or 30):
            w_status = 'nearing_expiry'
        elif w.warranty_type == 'extended':
            w_status = 'extended'
        else:
            w_status = 'active'
        w_dict['status'] = w_status

        if not status_filter or status_filter.lower() == w_status or (status_filter.lower() == 'active' and w_status in ['active', 'nearing_expiry', 'extended']):
            results.append(w_dict)

    return jsonify({'count': len(results), 'warranties': results}), 200


@warranties_bp.route('/', methods=['POST'])
@jwt_required()
def create_warranty():
    data = request.get_json() or {}
    product_id = data.get('product_id')
    if not product_id:
        return jsonify({'error': 'product_id is required.'}), 400

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found.'}), 404

    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and product.user_id != user_id:
        return jsonify({'error': 'Forbidden: You do not own this product.'}), 403

    try:
        start_date = parse_date_flexible(str(data['start_date'])) if data.get('start_date') else product.purchase_date
        expiry_date = parse_date_flexible(str(data['expiry_date'])) if data.get('expiry_date') else (start_date + timedelta(days=365))
    except Exception as e:
        return jsonify({'error': f'Invalid date format: {e}'}), 400

    warranty = Warranty(
        product_id=product_id,
        warranty_type=data.get('warranty_type', 'standard'),
        provider=data.get('provider', product.brand),
        start_date=start_date,
        expiry_date=expiry_date,
        coverage_conditions=data.get('coverage_conditions'),
        exclusions=data.get('exclusions'),
        service_center_details=data.get('service_center_details'),
        alert_days_before=int(data.get('alert_days_before', 30)),
    )
    db.session.add(warranty)
    db.session.commit()

    log_action(
        user_id=user_id,
        action_type='warranty_created',
        entity_type='warranty',
        entity_id=warranty.warranty_id,
        details={'product_id': product_id, 'type': warranty.warranty_type},
        ip_address=request.remote_addr,
    )

    return jsonify({'message': 'Warranty created.', 'warranty': warranty.to_dict()}), 201


@warranties_bp.route('/<warranty_id>', methods=['GET'])
@jwt_required()
def get_warranty(warranty_id):
    warranty = Warranty.query.get(warranty_id)
    if not warranty:
        return jsonify({'error': 'Warranty not found.'}), 404

    product = Product.query.get(warranty.product_id)
    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and product and product.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    return jsonify({'warranty': warranty.to_dict()}), 200


@warranties_bp.route('/product/<product_id>', methods=['GET'])
@jwt_required()
def get_product_warranties(product_id):
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found.'}), 404

    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and product.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    warranties = Warranty.query.filter_by(product_id=product_id).all()
    return jsonify({'count': len(warranties), 'warranties': [w.to_dict() for w in warranties]}), 200


@warranties_bp.route('/<warranty_id>', methods=['PUT'])
@role_required('admin', 'reviewer', 'service_employee')
def update_warranty(warranty_id):
    warranty = Warranty.query.get(warranty_id)
    if not warranty:
        return jsonify({'error': 'Warranty not found.'}), 404

    data = request.get_json() or {}
    for f in ['warranty_type', 'provider', 'coverage_conditions', 'exclusions', 'service_center_details']:
        if f in data:
            setattr(warranty, f, data[f])

    if 'expiry_date' in data:
        warranty.expiry_date = parse_date_flexible(str(data['expiry_date']))
    if 'alert_days_before' in data:
        warranty.alert_days_before = int(data['alert_days_before'])

    db.session.commit()
    return jsonify({'message': 'Warranty updated.', 'warranty': warranty.to_dict()}), 200


@warranties_bp.route('/expiring', methods=['GET'])
@jwt_required()
def get_expiring_warranties():
    """Trigger expiry checks and return warranties expiring within alert window."""
    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    alerts_triggered = check_warranty_expiry_alerts()
    days = int(request.args.get('days', 30))
    cutoff = date.today() + timedelta(days=days)

    query = Warranty.query.filter(
        Warranty.expiry_date >= date.today(),
        Warranty.expiry_date <= cutoff
    )

    if role == 'customer':
        query = query.join(Product).filter(Product.user_id == user_id)

    expiring = query.order_by(Warranty.expiry_date.asc()).all()

    return jsonify({
        'alerts_triggered': alerts_triggered,
        'count': len(expiring),
        'warranties': [w.to_dict() for w in expiring]
    }), 200

