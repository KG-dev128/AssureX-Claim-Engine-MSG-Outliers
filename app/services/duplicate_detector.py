"""
app/services/duplicate_detector.py
Deduplication engine for claims and document verification (FR xxx, xxxi).
Checks for duplicate invoices, duplicate file hashes, and repeated serial claims within 30 days.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List
from app.extensions import db
from app.models import Claim, Product, Document


def detect_duplicate_claim(claim_id: str) -> Dict[str, Any]:
    """
    Detect whether a claim is duplicate based on 3 distinct vectors:
    1. Document SHA-256 hash match against any other claim's documents
    2. Invoice number match in OCR metadata across claims
    3. Serial number match with similar fault reported within 30 days
    """
    claim = Claim.query.get(claim_id)
    if not claim:
        return {'is_duplicate': False, 'matched_claim_ids': [], 'reasons': []}

    product = Product.query.get(claim.product_id)
    claim_docs = Document.query.filter_by(claim_id=claim_id).all()

    matched_claim_ids = set()
    reasons = []

    # 1. Document SHA-256 Hash Matching
    for doc in claim_docs:
        if not doc.file_hash:
            continue
        existing_doc = Document.query.filter(
            Document.file_hash == doc.file_hash,
            Document.claim_id.isnot(None),
            Document.claim_id != claim_id
        ).first()

        if existing_doc and existing_doc.claim_id:
            matched_claim_ids.add(existing_doc.claim_id)
            reasons.append(f"Document '{doc.file_name or doc.doc_type}' has identical SHA-256 hash to file in claim #{existing_doc.claim_id[:8].upper()}")

    # 2. Invoice Number Matching via OCR
    for doc in claim_docs:
        if doc.ocr_extracted_data and isinstance(doc.ocr_extracted_data, dict):
            inv_num = doc.ocr_extracted_data.get('invoice_number')
            if inv_num and len(str(inv_num).strip()) > 3:
                # Query documents belonging to other claims
                other_docs = Document.query.filter(
                    Document.claim_id.isnot(None),
                    Document.claim_id != claim_id
                ).all()

                for other in other_docs:
                    if other.ocr_extracted_data and isinstance(other.ocr_extracted_data, dict):
                        if other.ocr_extracted_data.get('invoice_number') == inv_num:
                            matched_claim_ids.add(other.claim_id)
                            reasons.append(f"Invoice number '{inv_num}' already submitted in claim #{other.claim_id[:8].upper()}")

    # 3. Serial Number Repeated Within 30 Days
    if product and product.serial_number:
        cutoff = datetime.utcnow() - timedelta(days=30)
        recent_claims = Claim.query.join(Product).filter(
            Product.serial_number == product.serial_number,
            Claim.claim_id != claim_id,
            Claim.created_at >= cutoff
        ).all()

        for rc in recent_claims:
            matched_claim_ids.add(rc.claim_id)
            reasons.append(f"Serial number '{product.serial_number}' was already filed under claim #{rc.claim_id[:8].upper()} within 30 days")

    is_duplicate = len(matched_claim_ids) > 0

    # Persist flag on claim model
    claim.is_duplicate = is_duplicate
    db.session.commit()

    return {
        'is_duplicate': is_duplicate,
        'matched_claim_ids': list(matched_claim_ids),
        'reasons': reasons,
    }


def is_file_hash_duplicate(file_hash: str, exclude_claim_id: str = None) -> bool:
    """Check if a file with the given SHA-256 already exists in another claim."""
    query = Document.query.filter(Document.file_hash == file_hash)
    if exclude_claim_id:
        query = query.filter(Document.claim_id != exclude_claim_id)
    return query.first() is not None
