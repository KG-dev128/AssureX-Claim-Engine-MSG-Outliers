"""
ASSUREX - STEP 4
Multi-engine OCR for receipts, invoices, and warranty cards.

Engine priority (auto-fallback):
  1. PaddleOCR  - PP-OCRv4 (deep-learning, preferred)
  2. EasyOCR    - CRAFT + CRNN (fast, GPU optional)
  3. Tesseract  - legacy last-resort

Supported input: PDF, JPG, JPEG, PNG, BMP, TIFF, WEBP.
For PDFs, pdf2image is used to render pages before OCR.

Install:
    pip install paddlepaddle paddleocr easyocr pytesseract pillow pdf2image

Run standalone:
    python 04_receipt_ocr.py --doc path/to/receipt.jpg
    python 04_receipt_ocr.py --doc path/to/warranty.png --mode warranty
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import warnings
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
DEFAULT_CLAIM = OUTPUT_DIR / "step02_claim.json"
OUT_PATH = OUTPUT_DIR / "step04_ocr.json"


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def get_images(path: Path) -> list:
    """Return list of PIL.Image objects from an image or PDF file."""
    from PIL import Image
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}:
        return [Image.open(path).convert("RGB")]
    if suffix == ".pdf":
        try:
            from pdf2image import convert_from_path
            return convert_from_path(str(path), dpi=200, first_page=1, last_page=5)
        except Exception:
            raise ValueError("pdf2image required for PDF: pip install pdf2image")
    raise ValueError(f"Unsupported OCR input: {suffix}")


# ---------------------------------------------------------------------------
# OCR engine implementations
# ---------------------------------------------------------------------------

def _run_paddleocr(img_path: str) -> List[Tuple[str, float]]:
    """PaddleOCR 3.x via .predict() API. PP-OCRv4 avoids oneDNN/PIR bug."""
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(
        ocr_version="PP-OCRv4",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        lang="en",
    )
    results = ocr.predict(img_path)
    lines: List[Tuple[str, float]] = []
    for page in results:
        if not page:
            continue
        if isinstance(page, dict):
            texts = page.get("rec_texts", [])
            scores = page.get("rec_scores", [1.0] * len(texts))
            lines.extend(zip(texts, [float(s) for s in scores]))
        elif isinstance(page, list):
            for item in page:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    _, payload = item
                    if isinstance(payload, (list, tuple)) and len(payload) >= 2:
                        lines.append((str(payload[0]), float(payload[1])))
    return lines


@lru_cache(maxsize=1)
def _easyocr_reader():
    import easyocr
    return easyocr.Reader(["en"], gpu=False, verbose=False)


def _run_easyocr(img_path: str) -> List[Tuple[str, float]]:
    """EasyOCR – reliable fallback, no system dependencies."""
    reader = _easyocr_reader()
    raw = reader.readtext(img_path)
    return [(str(text), float(conf)) for (_, text, conf) in raw]


def _run_tesseract(img_path: str) -> List[Tuple[str, float]]:
    """Tesseract – legacy fallback."""
    import pytesseract
    from PIL import Image
    data = pytesseract.image_to_data(Image.open(img_path), output_type=pytesseract.Output.DICT)
    grouped = {}
    for index, text in enumerate(data["text"]):
        confidence = float(data["conf"][index]) / 100
        if text.strip() and confidence >= 0:
            key = tuple(data[k][index] for k in ("page_num", "block_num", "par_num", "line_num"))
            grouped.setdefault(key, []).append((text.strip(), confidence))
    return [(" ".join(word for word, _ in words), sum(c for _, c in words) / len(words)) for words in grouped.values()]


def run_ocr(img_path: str, engine: str = "auto") -> Tuple[List[Tuple[str, float]], str]:
    """
    Run OCR with automatic fallback chain.

    Args:
        img_path: Path to image file.
        engine: "auto", "paddleocr", "easyocr", or "tesseract".

    Returns:
        (lines, engine_used) where lines = [(text, confidence), ...]
    """
    chain_map = {
        "paddleocr": _run_paddleocr,
        "easyocr":   _run_easyocr,
        "tesseract": _run_tesseract,
    }
    order = [engine] if engine != "auto" and engine in chain_map else ["paddleocr", "easyocr", "tesseract"]
    last_err: Exception | None = None
    for eng in order:
        try:
            lines = chain_map[eng](img_path)
            if lines:
                return lines, eng
        except Exception as exc:
            last_err = exc
    raise RuntimeError(
        f"All OCR engines failed. Last error: {last_err}. "
        "Install: pip install paddlepaddle paddleocr easyocr"
    )


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

_DATE_RE            = re.compile(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]20\d{2})\b")
_SERIAL_RE          = re.compile(r"\b(?:SN|S/N|SERIAL(?:\s+NUMBER)?|SERIAL#)\s*[:\-#]?\s*([A-Z0-9\-]{4,})\b", re.I)
_INVOICE_RE         = re.compile(r"\b(?:invoice|inv)(?:\s*(?:number|num|no\.?|ref))?\s*[:\-#]?\s*([A-Z0-9\-]{4,})\b", re.I)
_AMOUNT_RE          = re.compile(r"(?:total|amount\s*paid|paid|grand\s*total)\s*[:\$\u20a8\u20ac\xa3\s]*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", re.I)
_WARRANTY_LEN_RE    = re.compile(r"\b(\d{1,3})\s*(days?|months?|years?)\b", re.I)
_WARRANTY_EXPIRY_RE = re.compile(r"warranty\s*expir(?:es?|y)\s*[:\-]?\s*(20\d{2}[-/]\d{1,2}[-/]\d{1,2})", re.I)
_PRODUCT_RE         = re.compile(r"product\s*[:\-]?\s*(.+)", re.I)
_MODEL_NUMBER_RE    = re.compile(r"(?:model(?:\s*(?:number|no\.?))?|model#)\s*[:\-#]?\s*([A-Z0-9][A-Z0-9._\-/]{2,})", re.I)
_OWNER_RE           = re.compile(r"(?:registered\s*owner|owner)\s*[:\-]?\s*(.+)", re.I)


def extract_receipt_fields(lines: List[Tuple[str, float]]) -> dict:
    """Extract structured fields from receipt / invoice OCR output."""
    text = "\n".join(t for t, _ in lines)
    dates = _DATE_RE.findall(text)
    serials = _SERIAL_RE.findall(text)
    invoices = _INVOICE_RE.findall(text)
    amounts = _AMOUNT_RE.findall(text)
    product_match = _PRODUCT_RE.search(text)
    model_match = _MODEL_NUMBER_RE.search(text)

    store_name = None
    purchase_date = dates[0] if dates else None
    invoice_number = invoices[0] if invoices else None
    serial_number = serials[0] if serials else None
    amount_paid = amounts[-1] if amounts else None
    warranty_months = None

    prev_label = ""
    for raw_text, conf in lines:
        clean = raw_text.strip()
        cl = clean.lower()
        if not clean:
            continue
        if any(k in cl for k in ("invoice number", "invoice no", "invoice ref")):
            prev_label = "invoice"
        elif any(k in cl for k in ("serial number", "serial#", "serial no")):
            prev_label = "serial"
        elif "purchase date" in cl:
            prev_label = "date"
        elif any(k in cl for k in ("amount paid", "grand total")):
            prev_label = "amount"
        elif any(k in cl for k in ("warranty period",)):
            prev_label = "warranty"
        elif prev_label == "invoice" and not invoice_number:
            invoice_number = clean; prev_label = ""
        elif prev_label == "serial" and not serial_number:
            serial_number = clean; prev_label = ""
        elif prev_label == "date" and _DATE_RE.search(clean):
            purchase_date = _DATE_RE.search(clean).group(1); prev_label = ""
        elif prev_label == "amount" and re.search(r"[0-9]", clean):
            amount_paid = re.sub(r"[^\d\.]", "", clean) or amount_paid; prev_label = ""
        elif prev_label == "warranty" and _WARRANTY_LEN_RE.search(clean):
            m = _WARRANTY_LEN_RE.search(clean)
            num, unit = int(m.group(1)), m.group(2).lower()
            warranty_months = num * 12 if "year" in unit else (round(num / 30) if "day" in unit else num)
            prev_label = ""

        # Store name: first high-confidence line not matching known keywords
        if store_name is None and conf >= 0.85:
            skip = {"invoice", "serial", "amount", "paid", "date", "receipt", "warranty", "branch", "total"}
            if not any(k in cl for k in skip) and len(clean) > 5 and re.match(r"[A-Z]", clean):
                store_name = clean

    return {
        "purchase_date":   purchase_date,
        "invoice_number":  invoice_number,
        "serial_number":   serial_number,
        "amount_paid":     amount_paid,
        "warranty_months": warranty_months,
        "store_name":      store_name or (lines[0][0].strip() if lines else None),
        "product_name":    product_match.group(1).strip() if product_match else None,
        "model_number":    model_match.group(1).strip() if model_match else None,
    }


def extract_warranty_fields(lines: List[Tuple[str, float]]) -> dict:
    """Extract structured fields from warranty card OCR output."""
    text = "\n".join(t for t, _ in lines)
    dates = _DATE_RE.findall(text)
    serials = _SERIAL_RE.findall(text)
    invoices = _INVOICE_RE.findall(text)
    expiry = _WARRANTY_EXPIRY_RE.search(text)
    product = _PRODUCT_RE.search(text)
    owner = _OWNER_RE.search(text)
    warranty_months = None
    period_match = re.search(r"warranty\s*period\s*[:\-]?\s*(\d+)\s*(days?|months?|years?)", text, re.I)
    if period_match:
        num, unit = int(period_match.group(1)), period_match.group(2).lower()
        warranty_months = num * 12 if "year" in unit else (round(num / 30) if "day" in unit else num)
    return {
        "serial_number":    serials[0] if serials else None,
        "invoice_ref":      invoices[0] if invoices else None,
        "purchase_date":    dates[0] if dates else None,
        "warranty_expiry":  expiry.group(1) if expiry else None,
        "warranty_months":  warranty_months,
        "product_name":     product.group(1).strip() if product else None,
        "registered_owner": owner.group(1).strip() if owner else None,
    }


def extract_fields(text: str) -> dict:
    """Legacy interface – accepts raw text string (used by app.py)."""
    lines = [(line, 1.0) for line in text.splitlines() if line.strip()]
    return extract_receipt_fields(lines)


# ---------------------------------------------------------------------------
# High-level document OCR entry-point
# ---------------------------------------------------------------------------

def ocr_document(file_path, mode: str = "receipt", engine: str = "auto") -> dict:
    """
    OCR a receipt or warranty card.

    Args:
        file_path: str or Path to image/PDF.
        mode: "receipt" or "warranty".
        engine: "auto" | "paddleocr" | "easyocr" | "tesseract".

    Returns:
        dict with raw_text, extracted_fields, engine_used, ocr_status, etc.
    """
    path = Path(file_path)
    images = get_images(path)
    all_lines: List[Tuple[str, float]] = []
    engine_used = "none"
    page_texts: list = []

    for idx, img in enumerate(images):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            img.save(tmp_path)
            page_lines, engine_used = run_ocr(tmp_path, engine=engine)
            all_lines.extend(page_lines)
            page_texts.append({
                "page": idx + 1,
                "lines": [{"text": t, "confidence": round(c, 4)} for t, c in page_lines],
            })
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    raw_text = "\n".join(t for t, _ in all_lines)
    extracted = extract_warranty_fields(all_lines) if mode == "warranty" else extract_receipt_fields(all_lines)

    return {
        "source_file":      str(path),
        "mode":             mode,
        "engine_used":      engine_used,
        "raw_text":         raw_text,
        "pages":            page_texts,
        "extracted_fields": extracted,
        "ocr_status":       "completed",
        "total_lines":      len(all_lines),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="AssureX Step 4 - multi-engine OCR")
    parser.add_argument("--doc",    help="Document image or PDF path")
    parser.add_argument("--claim",  default=str(DEFAULT_CLAIM))
    parser.add_argument("--mode",   choices=["receipt", "warranty"], default="receipt")
    parser.add_argument("--engine", choices=["auto", "paddleocr", "easyocr", "tesseract"], default="auto")
    parser.add_argument("--out",    default=str(OUT_PATH))
    args = parser.parse_args()

    if args.doc:
        doc_path = Path(args.doc)
    else:
        claim_path = Path(args.claim)
        if not claim_path.exists():
            raise SystemExit("Provide --doc <path> or run Step 2 first.")
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        doc_info = claim.get("documents", {}).get("purchase_receipt")
        if not doc_info:
            raise SystemExit("Purchase receipt not found in claim JSON.")
        doc_path = Path(doc_info["path"])

    if not doc_path.exists():
        raise SystemExit(f"File not found: {doc_path}")

    print(f"Running OCR [{args.mode} / {args.engine}]: {doc_path.name}")
    result = ocr_document(doc_path, mode=args.mode, engine=args.engine)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"\nEngine used : {result['engine_used']}")
    print(f"Lines found : {result['total_lines']}")
    print("\nExtracted fields:")
    for k, v in result["extracted_fields"].items():
        print(f"  {k}: {v}")
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
