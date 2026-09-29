"""
app/routes/ml.py
Machine Learning endpoints for Python tabular & GTM visual inference and version management (FR xviii, xxi, xlviii).
"""
import os
import json
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.extensions import db
from app.models import ModelVersion, ModelPrediction, Claim
from app.services.ml_service import predict_claim
from app.services.gtm_service import predict_gtm
from app.services.auth_service import role_required

ml_bp = Blueprint('ml', __name__)


@ml_bp.route('/predict-python/<claim_id>', methods=['POST'])
@jwt_required()
def run_python_prediction(claim_id):
    claim = Claim.query.get(claim_id)
    if not claim:
        return jsonify({'error': 'Claim not found.'}), 404
    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and claim.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    try:
        res = predict_claim(claim_id)
        return jsonify({'message': 'Python model prediction executed.', 'prediction': res}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@ml_bp.route('/predict-gtm/<claim_id>', methods=['POST'])
@jwt_required()
def run_gtm_prediction(claim_id):
    claim = Claim.query.get(claim_id)
    if not claim:
        return jsonify({'error': 'Claim not found.'}), 404
    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and claim.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    try:
        res = predict_gtm(claim_id)
        return jsonify({'message': 'GTM visual model prediction executed.', 'prediction': res}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400



@ml_bp.route('/versions', methods=['GET'])
@jwt_required()
def get_model_versions():
    """List registered model versions from database or versions.json."""
    db_versions = ModelVersion.query.all()
    if db_versions:
        return jsonify({'versions': [v.to_dict() for v in db_versions]}), 200

    ver_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ml', 'versions.json')
    if os.path.exists(ver_path):
        with open(ver_path, 'r') as f:
            versions = json.load(f)
        return jsonify({'versions': versions}), 200

    return jsonify({'versions': []}), 200


@ml_bp.route('/versions/<version_id>/activate', methods=['POST'])
@role_required('admin')
def activate_version(version_id):
    """Admin activation of a specific model version."""
    v = ModelVersion.query.get(version_id)
    if not v:
        return jsonify({'error': 'Version not found.'}), 404

    # Deactivate others of same type
    ModelVersion.query.filter_by(model_type=v.model_type).update({'is_active': False})
    v.is_active = True
    db.session.commit()

    return jsonify({'message': f"Version {v.version_tag} activated for {v.model_type}."}), 200
