"""
app/routes/reports.py
Report generation endpoints for PDF evaluations and CSV exports (FR xli, xlii).
"""
import os
from flask import Blueprint, request, jsonify, send_file, Response
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models import Claim
from app.services.report_generator import generate_claim_pdf_report, generate_claims_csv

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/claim/<claim_id>/pdf', methods=['GET'])
@jwt_required()
def export_claim_pdf(claim_id):
    claim = Claim.query.get(claim_id)
    if not claim:
        return jsonify({'error': 'Claim not found.'}), 404

    user_id = get_jwt_identity()
    role = get_jwt().get('role', 'customer')
    if role == 'customer' and claim.user_id != user_id:
        return jsonify({'error': 'Forbidden.'}), 403

    try:
        report_file = generate_claim_pdf_report(claim_id)
        abs_report_file = os.path.abspath(report_file)
        if os.path.exists(abs_report_file):
            mime = 'application/pdf' if abs_report_file.endswith('.pdf') else 'text/plain'
            return send_file(
                abs_report_file,
                mimetype=mime,
                as_attachment=True,
                download_name=os.path.basename(abs_report_file)
            )
        return jsonify({'error': 'Report file could not be located.'}), 500
    except Exception as e:
        return jsonify({'error': f'Failed to generate report: {e}'}), 500



@reports_bp.route('/claims/csv', methods=['GET'])
@jwt_required()
def export_claims_csv():
    user_id = get_jwt_identity()
    claims_jwt = get_jwt()
    role = claims_jwt.get('role', 'customer')

    target_user = user_id if role == 'customer' else request.args.get('user_id')
    csv_stream = generate_claims_csv(user_id=target_user)

    return Response(
        csv_stream.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=assurex_claims_export.csv"}
    )
