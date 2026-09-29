"""
app/services/ocr_service.py
Optical Character Recognition (OCR) pipeline for document parsing (FR vi, vii).
Extracts purchase date, invoice number, serial number, model number, purchase price,
and warranty duration using EasyOCR with graceful fallback parsers.
"""
import os
import re
from typing import Dict, Any, List, Optional
from app.extensions import db
from app.models import Document
from app.services.audit_service import log_action

_reader = None


def get_ocr_reader():
    """Lazy initialize EasyOCR reader singleton."""
    global _reader
    if _reader is None:
        try:
            import easyocr
            _reader = easyocr.Reader(['en'], gpu=False)
        except Exception as e:
            print(f"[OCR] EasyOCR unavailable or model loading failed: {e}")
            _reader = None
    return _reader


def extract_raw_text(file_path: str, mime_type: str = "") -> List[str]:
    """
    Extract lines/tokens from document file.
    Supports EasyOCR on images and PDFs (via pypdfium2 / pdf2image if installed).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    results = []
    reader = get_ocr_reader()

    if reader is not None:
        try:
            ext = file_path.rsplit('.', 1)[-1].lower()
            if ext == 'pdf' or 'pdf' in mime_type:
                try:
                    import pypdfium2 as pdfium
                    import numpy as np
                    doc = pdfium.PdfDocument(file_path)
                    for page in doc:
                        bitmap = page.render(scale=2.0)
                        pil_img = bitmap.to_pil()
                        page_res = reader.readtext(np.array(pil_img), detail=0)
                        results.extend(page_res)
                except ImportError:
                    # Alternative pypdf raw text extraction if image rasterizer not present
                    try:
                        import pypdf
                        reader_pdf = pypdf.PdfReader(file_path)
                        for page in reader_pdf.pages:
                            text = page.extract_text()
                            if text:
                                results.extend(text.splitlines())
                    except Exception:
                        pass
            else:
                # Regular image
                results = reader.readtext(file_path, detail=0)
        except Exception as e:
            print(f"[OCR] Reader extraction error: {e}")

    # If EasyOCR returned nothing or wasn't loaded, try reading raw text directly if text-based
    if not results:
        try:
            with open(file_path, 'r', errors='ignore') as f:
                content = f.read(4096)
                if content:
                    results = content.splitlines()
        except Exception:
            pass

    return [str(r).strip() for r in results if str(r).strip()]


def parse_ocr_fields(text_lines: List[str]) -> Dict[str, Any]:
    """
    Structured field parser using regex heuristics matching FR vi:
    - purchase_date
    - invoice_number
    - serial_number
    - model_number
    - purchase_amount
    - warranty_duration
    """
    full_text = " ".join(text_lines)

    extracted = {
        'purchase_date': None,
        'invoice_number': None,
        'serial_number': None,
        'model_number': None,
        'purchase_amount': None,
        'warranty_duration': None,
        'raw_text_snippet': full_text[:500] if full_text else "",
    }

    # 1. Purchase Date
    date_patterns = [
        r'\b(?:Date|Dated|Purchase\s*Date)[\s:]*([0-9]{4}[/-][0-9]{2}[/-][0-9]{2})\b',
        r'\b(?:Date|Dated|Purchase\s*Date)[\s:]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{4})\b',
        r'\b([0-9]{4}[/-][0-9]{2}[/-][0-9]{2})\b',
        r'\b([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{4})\b',
        r'\b([0-9]{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+[0-9]{4})\b',
    ]
    for pat in date_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            extracted['purchase_date'] = m.group(1).strip()
            break

    # 2. Invoice Number
    inv_patterns = [
        r'(?:Invoice|Inv|Bill|Receipt)[\s#No.:\-]+([A-Z0-9\-]{4,20})',
        r'#\s*([0-9]{4,12})\b',
    ]
    for pat in inv_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            extracted['invoice_number'] = m.group(1).strip()
            break

    # 3. Serial Number
    sn_patterns = [
        r'(?:Serial|S/N|SN|Serial\s*No\.?)[\s:#\-]+([A-Z0-9\-]{5,25})',
        r'\bSN-([A-Z0-9]{6,16})\b',
    ]
    for pat in sn_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            extracted['serial_number'] = m.group(1).strip()
            break

    # 4. Model Number
    model_patterns = [
        r'(?:Model|Mod|Model\s*No\.?)[\s:#\-]+([A-Z0-9\-]{3,20})',
    ]
    for pat in model_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            extracted['model_number'] = m.group(1).strip()
            break

    # 5. Purchase Amount
    amount_patterns = [
        r'(?:Total|Grand\s*Total|Amount|Price|Paid)[\s:$€£]*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)',
        r'[$€£]\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)',
    ]
    for pat in amount_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            extracted['purchase_amount'] = m.group(1).replace(',', '').strip()
            break

    # 6. Warranty Duration
    warranty_patterns = [
        r'([0-9]+)\s*(?:years?|yrs?|months?|mos?)\s*warranty',
        r'warranty[\s:]*([0-9]+)\s*(?:years?|yrs?|months?|mos?)',
    ]
    for pat in warranty_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            extracted['warranty_duration'] = m.group(0).strip()
            break

    return extracted


def run_ocr_for_document(doc_id: str) -> Dict[str, Any]:
    """
    Process OCR for a stored document record, update database, and return extracted fields.
    """
    doc = Document.query.get(doc_id)
    if not doc:
        raise ValueError(f"Document #{doc_id} not found.")

    doc.ocr_status = 'processing'
    db.session.commit()

    try:
        raw_lines = extract_raw_text(doc.file_path, doc.mime_type or '')
        extracted_data = parse_ocr_fields(raw_lines)
        doc.ocr_extracted_data = extracted_data
        doc.ocr_status = 'completed'
        db.session.commit()

        log_action(
            user_id=doc.user_id,
            action_type='ocr_extracted',
            entity_type='document',
            entity_id=doc.doc_id,
            details=extracted_data,
        )

        return extracted_data
    except Exception as e:
        doc.ocr_status = 'failed'
        db.session.commit()
        raise e
