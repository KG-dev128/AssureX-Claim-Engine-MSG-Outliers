"""
app/services/ml_service.py
Tabular ML model inference service (FR xviii, xix).
Preprocesses claim attributes, executes trained classifier, persists predictions,
and outputs 3-class probabilities (valid, invalid, manual_review).
"""
import os
import json
import numpy as np
import joblib
from typing import Dict, Any, Optional
from app.extensions import db
from app.models import Claim, Product, Warranty, ModelPrediction, ModelVersion
from app.services.audit_service import log_action
from app.services.preprocessing_service import build_feature_dict

_artifacts = None


def ensure_model_versions_seeded():
    """Ensure active model versions from versions.json are present in NeonDB model_versions table."""
    ver_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ml', 'versions.json')
    if not os.path.exists(ver_path):
        return
    try:
        with open(ver_path, 'r') as f:
            versions = json.load(f)
        for v in versions:
            vid = v.get('version_id')
            if not vid:
                continue
            existing = ModelVersion.query.get(vid)
            if not existing:
                mv = ModelVersion(
                    version_id=vid,
                    model_type=v.get('model_type', 'python'),
                    version_tag=v.get('version_tag', 'v1.0'),
                    algorithm=v.get('algorithm', 'Unknown'),
                    accuracy=v.get('accuracy'),
                    f1_score=v.get('f1_score'),
                    model_file_path=v.get('model_file_path'),
                    is_active=v.get('is_active', True)
                )
                db.session.add(mv)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[MLService] Notice: could not seed model versions ({e})")


def get_artifacts():
    """Lazy-load and cache production model and preprocessors."""
    global _artifacts
    if _artifacts is not None:
        return _artifacts

    model_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ml', 'models')
    model_path = os.path.join(model_dir, 'best_model.pkl')
    scaler_path = os.path.join(model_dir, 'scaler.pkl')
    encoder_path = os.path.join(model_dir, 'label_encoder.pkl')
    target_path = os.path.join(model_dir, 'target_encoder.pkl')
    cols_path = os.path.join(model_dir, 'feature_columns.json')
    ver_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ml', 'versions.json')

    if not os.path.exists(model_path):
        return None

    try:
        model = joblib.load(model_path)
        scaler = joblib.load(scaler_path)
        encoders = joblib.load(encoder_path)
        target_encoder = joblib.load(target_path) if os.path.exists(target_path) else None

        with open(cols_path, 'r') as f:
            feature_cols = json.load(f)

        version_id = None
        if os.path.exists(ver_path):
            with open(ver_path, 'r') as f:
                versions = json.load(f)
                for v in versions:
                    if v.get('model_type') == 'python' and v.get('is_active'):
                        version_id = v.get('version_id')
                        break

        _artifacts = {
            'model': model,
            'scaler': scaler,
            'encoders': encoders,
            'target_encoder': target_encoder,
            'feature_cols': feature_cols,
            'version_id': version_id,
        }
        return _artifacts
    except Exception as e:
        print(f"[MLService] Error loading model artifacts: {e}")
        return None


def transform_features(features: Dict[str, Any], artifacts: Dict[str, Any]) -> np.ndarray:
    """Transforms raw dictionary into scaled feature array."""
    cols = artifacts['feature_cols']
    encoders = artifacts['encoders']
    scaler = artifacts['scaler']

    row = []
    for col in cols:
        val = features.get(col, 0)
        if col in encoders:
            le = encoders[col]
            sval = str(val)
            if sval in le.classes_:
                encoded_val = le.transform([sval])[0]
            else:
                encoded_val = 0
            row.append(float(encoded_val))
        elif isinstance(val, bool):
            row.append(1.0 if val else 0.0)
        else:
            try:
                row.append(float(val))
            except (ValueError, TypeError):
                row.append(0.0)

    X = np.array(row, dtype=np.float32).reshape(1, -1)
    return scaler.transform(X)


def predict_claim(claim_id: str) -> Dict[str, Any]:
    """
    Execute tabular ML model prediction for a given claim.
    Returns:
        {
            'predicted_class': 'valid' | 'invalid' | 'manual_review',
            'confidence_valid': float,
            'confidence_invalid': float,
            'confidence_manual_review': float,
            'model_type': 'python',
            'model_version_id': str,
        }
    """
    claim = Claim.query.get(claim_id)
    if not claim:
        raise ValueError(f"Claim #{claim_id} not found.")

    product = Product.query.get(claim.product_id)
    warranty = Warranty.query.get(claim.warranty_id)
    features = build_feature_dict(claim_id)

    # Align feature dictionary keys with training columns
    enriched_features = dict(features)
    enriched_features['warranty_duration_days'] = float((product.warranty_duration_months or 12) * 30 if product else 365)
    enriched_features['label'] = 'unknown'

    artifacts = get_artifacts()

    if artifacts is None:
        # Calibrated baseline heuristic fallback if model weights are not loaded yet
        is_active = features['is_warranty_active'] == 1.0
        no_dup = features['is_duplicate'] == 0.0
        no_contra = features['contradiction_count'] == 0.0
        has_rec = features['has_purchase_receipt'] == 1.0
        not_excl = features['is_excluded_damage'] == 0.0

        if is_active and no_dup and no_contra and has_rec and not_excl:
            pred_class = 'valid'
            p_val, p_inv, p_mr = 0.88, 0.04, 0.08
        elif not is_active or not not_excl or not no_dup:
            pred_class = 'invalid'
            p_val, p_inv, p_mr = 0.03, 0.89, 0.08
        else:
            pred_class = 'manual_review'
            p_val, p_inv, p_mr = 0.20, 0.20, 0.60

        version_id = None
    else:
        model = artifacts['model']
        target_encoder = artifacts['target_encoder']
        X = transform_features(enriched_features, artifacts)

        probs = model.predict_proba(X)[0]
        classes = target_encoder.classes_ if target_encoder else ['valid', 'invalid', 'manual_review']

        prob_dict = {cls: float(probs[i]) for i, cls in enumerate(classes)}
        p_val = prob_dict.get('valid', 0.0)
        p_inv = prob_dict.get('invalid', 0.0)
        p_mr = prob_dict.get('manual_review', 0.0)

        pred_idx = np.argmax(probs)
        pred_class = classes[pred_idx]
        version_id = artifacts['version_id']

    # Ensure model_version exists in database table to satisfy foreign key constraint
    final_version_id = None
    if version_id:
        v_rec = ModelVersion.query.get(version_id)
        if not v_rec:
            ensure_model_versions_seeded()
            v_rec = ModelVersion.query.get(version_id)
        if v_rec:
            final_version_id = version_id

    # Persist in model_predictions table
    prediction_record = ModelPrediction(
        claim_id=claim_id,
        model_type='python',
        model_version_id=final_version_id,
        predicted_class=pred_class,
        confidence_valid=round(p_val, 4),
        confidence_invalid=round(p_inv, 4),
        confidence_manual_review=round(p_mr, 4),
        raw_input_features=features,
    )
    db.session.add(prediction_record)
    db.session.commit()

    log_action(
        user_id=claim.user_id,
        action_type='model_predicted_python',
        entity_type='model_prediction',
        entity_id=prediction_record.prediction_id,
        details={
            'predicted_class': pred_class,
            'confidence_valid': round(p_val, 4),
            'confidence_invalid': round(p_inv, 4),
            'confidence_manual_review': round(p_mr, 4),
        }
    )

    return {
        'prediction_id': prediction_record.prediction_id,
        'claim_id': claim_id,
        'predicted_class': pred_class,
        'confidence_valid': round(p_val, 4),
        'confidence_invalid': round(p_inv, 4),
        'confidence_manual_review': round(p_mr, 4),
        'model_type': 'python',
        'model_version_id': version_id,
    }
