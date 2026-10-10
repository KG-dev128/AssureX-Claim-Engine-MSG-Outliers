"""
app/routes/documents.py
Document upload, secure storage, OCR execution, and manual corrections (FR v, vi, vii).
"""
import os
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.extensions import db
from app.models import Document, Claim, Product
from app.utils.file_handler import save_secure_upload
from app.services.ocr_service import run_ocr_for_document
from app.services.audit_service import log_action

documents_bp = Blueprint('documents', __name__)


@documents_bp.route('/upload', methods=['POST'])
@documents_bp.route('/ocr', methods=['POST'])
@jwt_required()
def upload_document():
    user_id = get_jwt_identity()
    claims_jwt = get_jwt()
    role = claims_jwt.get('role', 'customer')

    if 'file' not in request.files:
        return jsonify({'error': 'No file part in request.'}), 400

    file_obj = request.files['file']
    doc_type = request.form.get('doc_type', 'receipt')
    claim_id = request.form.get('claim_id')
    product_id = request.form.get('product_id')

    if claim_id:
        c = Claim.query.get(claim_id)
        if not c:
            return jsonify({'error': 'Associated claim not found.'}), 404
        if role == 'customer' and c.user_id != user_id:
            return jsonify({'error': 'Forbidden: You do not own this claim.'}), 403

    if product_id:
        p = Product.query.get(product_id)
        if not p:
            return jsonify({'error': 'Associated product not found.'}), 404
        if role == 'customer' and p.user_id != user_id:
            return jsonify({'error': 'Forbidden: You do not own this product.'}), 403

    subfolder = claim_id if claim_id else (product_id if product_id else user_id)

    try:
        saved_info = save_secure_upload(file_obj, subfolder=subfolder)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    doc = Document(
        user_id=user_id,
        claim_id=claim_id,
        product_id=product_id,
        doc_type=doc_type,
        file_name=saved_info['file_name'],
        file_path=saved_info['file_path'],
        file_hash=saved_info['file_hash'],
        file_size=saved_info['file_size'],
        mime_type=saved_info['mime_type'],
        ocr_status='pending',
    )
    db.session.add(doc)
    db.session.commit()

    log_action(
        user_id=user_id,
        action_type='document_uploaded',
        entity_type='document',
        entity_id=doc.doc_id,
        details={'file_name': doc.file_name, 'file_hash': doc.file_hash, 'doc_type': doc_type},
        ip_address=request.remote_addr,
    )

    # Automatically trigger OCR for receipts, invoices, and warranty cards
    ocr_result = None
    if doc_type in ['receipt', 'invoice', 'warranty_card', 'other']:
        try:
            ocr_result = run_ocr_for_document(doc.doc_id)
        except Exception as e:
            print(f"[Document Route] OCR error: {e}")

    return jsonify({
        'message': 'Document uploaded successfully.',
        'document': doc.to_dict(),
        'ocr_extracted': ocr_result,
        'ocr_extracted_data': ocr_result,
    }), 201


@documents_bp.route('/', methods=['GET'])
@documents_bp.route('', methods=['GET'])
@jwt_required()
def list_documents():
    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role in ['admin', 'reviewer']:
        docs = Document.query.order_by(Document.uploaded_at.desc()).all()
    else:
        docs = Document.query.filter_by(user_id=user_id).order_by(Document.uploaded_at.desc()).all()
    return jsonify({'count': len(docs), 'documents': [d.to_dict() for d in docs]}), 200



@documents_bp.route('/<doc_id>', methods=['GET'])
@jwt_required()
def get_document(doc_id):
    doc = Document.query.get(doc_id)
    if not doc:
        return jsonify({'error': 'Document not found.'}), 404

    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and doc.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    # If raw file download requested
    if request.args.get('download') == 'true' and os.path.exists(doc.file_path):
        return send_file(os.path.abspath(doc.file_path), mimetype=doc.mime_type)

    return jsonify({'document': doc.to_dict()}), 200


@documents_bp.route('/claim/<claim_id>', methods=['GET'])
@jwt_required()
def get_claim_documents(claim_id):
    claim = Claim.query.get(claim_id)
    if not claim:
        return jsonify({'error': 'Claim not found.'}), 404

    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and claim.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    docs = Document.query.filter_by(claim_id=claim_id).all()
    return jsonify({'count': len(docs), 'documents': [d.to_dict() for d in docs]}), 200


@documents_bp.route('/<doc_id>/ocr', methods=['POST'])
@jwt_required()
def trigger_ocr(doc_id):
    doc = Document.query.get(doc_id)
    if not doc:
        return jsonify({'error': 'Document not found.'}), 404

    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and doc.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    try:
        extracted = run_ocr_for_document(doc_id)
        return jsonify({
            'message': 'OCR processing completed.',
            'ocr_extracted_data': extracted,
            'status': doc.ocr_status
        }), 200
    except Exception as e:
        return jsonify({'error': f'OCR failed: {e}', 'status': 'failed'}), 500


@documents_bp.route('/<doc_id>/ocr-correct', methods=['PUT'])
@jwt_required()
def correct_ocr_data(doc_id):
    """Allow user or reviewer to override/correct OCR extracted fields (FR vii)."""
    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    doc = Document.query.get(doc_id)
    if not doc:
        return jsonify({'error': 'Document not found.'}), 404

    if role == 'customer' and doc.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    data = request.get_json() or {}
    current_data = doc.ocr_extracted_data or {}
    current_data.update(data)
    doc.ocr_extracted_data = current_data
    db.session.commit()

    log_action(
        user_id=user_id,
        action_type='ocr_data_corrected',
        entity_type='document',
        entity_id=doc.doc_id,
        details=data,
        ip_address=request.remote_addr,
    )

    return jsonify({
        'message': 'OCR data corrected successfully.',
        'document': doc.to_dict()
    }), 200

