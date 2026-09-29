"""
app/routes/search.py
Advanced multi-criteria search endpoints (FR xliii).
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models import Claim, Product, Document

search_bp = Blueprint('search', __name__)


@search_bp.route('/track', methods=['GET'])
def track_claim_public():
    """
    Public tracking endpoint for claimants to check status by Claim ID or Serial Number.
    Does not expose confidential personal data or fraud scores.
    """
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'error': 'Tracking query is required.'}), 400

    claim = Claim.query.join(Product).filter(
        (Claim.claim_id == q) | (Product.serial_number == q)
    ).first()

    if not claim:
        return jsonify({'claims': [], 'found': False, 'message': f'No active claim found for "{q}".'}), 404

    tracking_data = {
        'claim_id': claim.claim_id,
        'status': claim.status.replace('_', ' ').title(),
        'damage_type': claim.damage_type,
        'created_at': claim.created_at.isoformat(),
        'product_name': claim.product.product_name if claim.product else 'Registered Unit',
        'recommendation': claim.status.replace('_', ' ').title(),
    }

    return jsonify({
        'found': True,
        'claims': [tracking_data],
        'claim': tracking_data,
        'results': [tracking_data],
    }), 200


@search_bp.route('/claims', methods=['GET'])
@jwt_required()
def search_claims():
    q = request.args.get('q', '').strip()
    status = request.args.get('status')
    category = request.args.get('category')
    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')

    query = Claim.query.join(Product)

    if role == 'customer':
        query = query.filter(Claim.user_id == user_id)

    if q:
        like_term = f"%{q}%"
        query = query.filter(
            (Claim.claim_id.ilike(like_term)) |
            (Claim.fault_description.ilike(like_term)) |
            (Claim.damage_type.ilike(like_term)) |
            (Product.serial_number.ilike(like_term)) |
            (Product.product_name.ilike(like_term)) |
            (Product.brand.ilike(like_term))
        )

    if status:
        query = query.filter(Claim.status == status)

    if category:
        query = query.filter(Product.category == category.lower())

    results = query.order_by(Claim.created_at.desc()).limit(50).all()
    results_dict = [c.to_dict() for c in results]
    return jsonify({
        'query': q,
        'count': len(results),
        'results': results_dict,
        'claims': results_dict,
    }), 200



@search_bp.route('/products', methods=['GET'])
@jwt_required()
def search_products():
    q = request.args.get('q', '').strip()
    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')

    query = Product.query
    if role == 'customer':
        query = query.filter_by(user_id=user_id)

    if q:
        like_term = f"%{q}%"
        query = query.filter(
            (Product.product_name.ilike(like_term)) |
            (Product.brand.ilike(like_term)) |
            (Product.model_number.ilike(like_term)) |
            (Product.serial_number.ilike(like_term)) |
            (Product.category.ilike(like_term))
        )

    results = query.order_by(Product.created_at.desc()).limit(50).all()
    return jsonify({
        'query': q,
        'count': len(results),
        'results': [p.to_dict() for p in results]
    }), 200
