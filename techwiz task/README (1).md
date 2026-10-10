# Historical scripts package — use README.md for the current web application

This document describes an earlier standalone 10-step scripts workflow. The
current Flask app, frontend, and setup instructions are documented in
[`README.md`](README.md). Do not use this historical guide to start or update
the current web interface.

---

# AssureX Claim Engine — Complete 10-Step Scripts Package

This package combines the original AssureX 10-step scripts with the corrected ML-compatible scripts and all 8 configurable warranty policies.

The flow is:

```text
01 Login + Product Selection
        ↓
02 Fault Details + Uploads
        ↓
03 SHA-256 Document Fingerprinting
        ↓
04 Receipt OCR (Tesseract)
        ↓
05 Human OCR Verification
        ↓
06A Corrected Python ML Prediction
        ↓
06B 800×600 Claim Summary Card + Teachable Machine
        ↓
07 Python vs TM Comparison / Arbiter
        ↓
08 Warranty Rule Engine
        ↓
09 Final Master Decision
        ↓
10 Manual Review + Hash-Chained Audit + PDF Certificate
```

## Included Files

### Step scripts

- `01_account_login_product.py`
- `02_claim_input_uploads.py`
- `03_document_fingerprint.py`
- `04_receipt_ocr.py`
- `05_ocr_verification.py`
- `06_ai_paths.py` — updated for the leakage-corrected Python ML model
- `06b_teachable_machine_inference.py` — independent TM inference adapter
- `07_compare_models.py`
- `08_warranty_rule_engine.py` — supports all 8 policy categories
- `09_final_master_decision.py`
- `10_manual_review_and_pdf.py`

### Warranty policies

`policies/` contains:

- `refrigerator_policy.json`
- `ac_policy.json`
- `microwave_policy.json`
- `smartphone_policy.json`
- `washing_machine_policy.json`
- `laptop_policy.json`
- `printer_policy.json`
- `television_policy.json`

These are project/demo configuration policies, not official manufacturer warranty terms.

### Data

- `data/assurex_claims_full_1500(4).csv`
- `data/example_tm_prediction.json`

The CSV is the 1,500-record AssureX dataset used by the corrected ML notebook.

## 1. Installation

Create a virtual environment:

### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install Python packages:

```bash
pip install -r requirements.txt
```

## 2. OCR System Requirements

`pytesseract` is the Python wrapper. The Tesseract OCR application itself must also be installed and available on PATH.

For PDF receipts, `pdf2image` may require Poppler to be installed on the machine.

## 3. Corrected Python ML Model

`06_ai_paths.py` is aligned with the corrected ML notebook. It expects the trained model and label encoder produced by that notebook, typically:

```text
models/best_corrected_assurex_model.joblib
models/corrected_label_encoder.joblib
```

The corrected notebook uses 25 prediction-time features and the class mapping:

```text
Invalid Claim
Manual Review
Valid Claim
```

Do not replace the model with a model trained using a different feature schema unless the inference mapping is updated to match it.

## 4. Teachable Machine

The TM model remains independent from the Python model.

A typical exported Teachable Machine image model uses:

```text
models/keras_model.h5
models/labels.txt
```

Run:

```bash
python 06b_teachable_machine_inference.py \
  --model models/keras_model.h5 \
  --labels models/labels.txt \
  --card outputs/claim_summary_card_800x600.png \
  --claim-id CLM-0001
```

The output should contain confidence values for all three AssureX classes.

The Claim Summary Card must not contain Python prediction, Python confidence, TM prediction, or final decision text before TM inference.

## 5. Running the 10 Steps

Run the scripts in order. Each script reads the previous step's JSON/file outputs.

```bash
python 01_account_login_product.py
python 02_claim_input_uploads.py
python 03_document_fingerprint.py
python 04_receipt_ocr.py
python 05_ocr_verification.py
python 06_ai_paths.py
python 06b_teachable_machine_inference.py
python 07_compare_models.py
python 08_warranty_rule_engine.py
python 09_final_master_decision.py
python 10_manual_review_and_pdf.py
```

Use `--help` on each script to see its exact arguments and paths.

## 6. Warranty Policies

Step 8 automatically maps product category to the corresponding policy file.

Supported categories:

```text
refrigerator
ac / air conditioner
microwave
smartphone
washing machine
laptop
printer
television / tv
```

The policies contain configurable fields for coverage duration, start conditions, covered faults, exclusions, reporting period, repair conditions, authorized service centers, replacement conditions, grace period, mandatory documents, hard-fail rules, warnings, and manual-review rules.

## 7. Model Comparison

Step 7 compares the independent Python and TM outputs.

It records:

- Python predicted class
- Python confidence for all 3 classes
- TM predicted class
- TM confidence for all 3 classes
- class-match status
- absolute top-class confidence difference
- consistency status

For the competition comparison deliverable, run this over at least 30 unseen test claims.

## 8. Final Decision

Step 9 produces only one of:

```text
Likely Valid
Likely Invalid
Manual Review Required
```

The final result uses model outputs together with rule results, missing evidence, contradiction indicators and duplicate indicators.

## 9. Manual Review and Audit

When manual review is required, Step 10 records:

- original AI predictions and confidences
- consistency/confidence difference
- warranty/rule information
- reviewer identity
- reviewer action
- mandatory review reason
- audit record hash

The script also generates a branded PDF audit certificate.

## 10. Important SRS Alignment

This package follows the supplied AssureX requirements for:

- three claim classes
- independent Python and Teachable Machine models
- common claim information in tabular and visual formats
- Claim Summary Cards without AI-result leakage
- configurable warranty policies
- contradiction/missing-document/duplicate checks
- confidence comparison
- at least 30 unseen comparison claims
- manual review
- reviewer override/history
- audit/report generation

## 11. Security / Production Note

This is a modular project prototype. A real deployment should additionally implement secure authentication/session management, database transactions, access control, secure file storage, malware/upload scanning, encryption, rate limiting, structured logs and proper secret management.

Do not place real customer personal information or confidential documents in the repository.
