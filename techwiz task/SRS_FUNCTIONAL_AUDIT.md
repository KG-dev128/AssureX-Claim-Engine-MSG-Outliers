# AssureX SRS Functional Requirements Audit

**Reviewed:** 2026-09-27  
**Basis:** SRS v1.0, section 1.6 (i–l), source inspection of `app.py`, frontend pages, pipeline modules, policy/data/model files, and the existing integration suite. This is a code-and-test review; it is not a production load, security, or user-acceptance test.

**Status key:** **Working** means there is an implemented end-to-end path or direct evidence; **Partial** means a feature exists but a stated SRS condition is missing, incomplete, or cannot be exercised with the supplied assets; **Missing** means no working application path was found.

| SRS | Status | Finding |
|---|---|---|
| i. Registration, authentication, role access | Partial | JWT sessions and server-side role gates exist for `user`, `admin`, `reviewer`, and `service_center`. Public signup creates customer accounts; staff accounts are provisioned by an admin. This is safer than allowing self-selected privileged roles, but it differs from the SRS wording that all four roles register themselves. |
| ii. User profile management | Working | Unique user ID, name, phone/contact, and password can be updated and are audit logged. |
| iii. Product registration | Working | Product form/API persist name, category, brand, model, serial, purchase date/price, retailer, and warranty duration with a product ID. |
| iv. Warranty record management | Working | Owners can add standard and extended warranty records with provider, coverage dates, terms, exclusions, and service-center contact details. The SRS does not provide a verified provider directory. |
| v. Receipt/invoice upload | Working | Intake validates and stores evidence; owners can list, download, add, replace, or remove documents before assessment or while responding to an information request. Each change is audited and duplicate evidence is flagged. |
| vi. Receipt scanning/data extraction | Partial | OCR extracts invoice, serial, date, amount, retailer, duration, product, and model hints. Layout-dependent fields remain suggestions and must be checked by the claimant. |
| vii. Extracted-data verification | Working | The intake flow displays source text and lets the customer correct extracted values before evaluation. |
| viii. Warranty tracking | Working | Start/expiry dates are calculated; active, near-expiry, and expired states are exposed, including extended warranty data. |
| ix. Warranty expiry alerts | Working | A background scheduler creates idempotent in-app notifications at startup and daily thereafter; its last run is recorded and visible to admins. |
| x. Claim registration | Working | Customers and authenticated service-center staff can create claims for an existing customer and registered product; owner notifications and staff audit events are recorded. |
| xi. Claim information collection | Partial | Intake stores product, purchase, fault, damage, repair, and replacement facts, including replacement date/details and policy-based reporting deadline. Some details remain in the claim JSON rather than normalized database columns. |
| xii. Fault/damage evidence upload | Working | Product, serial, repair, and fault images/PDFs plus MP4, MOV, or WebM fault video can be uploaded under the configured size limit. Video is retained for reviewer viewing and is not passed to OCR. |
| xiii. Repair history management | Working | Customers and service-center staff can record dated repairs with center, parts, outcome, cost, and authorization; records are linked to the product and audit trail. |
| xiv. Document organization | Working | A claim evidence library supports list/download/add/replace/remove with owner/staff authorization, file-path checks, hashes, audit events, and packaged report download. Changes are locked after final assessment except when a reviewer requests information. |
| xv. Data validation | Working | Required claim text/date fields, supported file types and total size, warranty terms, serial uniqueness, dates, numeric ranges, and claim IDs are checked. Policy evidence gaps are explicitly surfaced and routed for review. |
| xvi. Data preprocessing | Working | A saved preprocessing pipeline and live feature preparation handle categorical/numeric features and derived fields for the Python classifier. |
| xvii. Common claim dataset | Working | A reproducible generator creates claim cards from the supplied 1,500-row SRS dataset. The 70/15/15 split is stratified, claim-level, and includes 2,100 training variations plus 225 validation and 225 test cards. Class mapping and per-card provenance are explicit. |
| xviii. Python classification model | Working | The notebook compares Logistic Regression, Random Forest, and XGBoost; saved pipelines/models are integrated. The existing results file records test accuracies of 95.11%, 88.44%, and 93.33%, respectively. |
| xix. Python confidence scores | Working | The integrated model returns probabilities for all three classes; the real-pipeline test verifies the confidence values. |
| xx. Claim Summary Card | Working | A standardized card generator exists and is designed to omit model predictions and final decisions. |
| xxi. Image-model classification / Teachable Machine | Partial | The app uses a working in-house HOG + multinomial logistic regression image classifier with SRS labels, version hashes, and held-out evaluation. The supplied H5 has only `Class 1/2/3`; no trusted class mapping or Teachable Machine export was supplied, so Google TM-specific integration remains unverified. |
| xxii. Prediction comparison | Working | Runtime compares the corrected tabular model and the independent claim-card image model when both are available. |
| xxiii. Confidence comparison | Working | Both models return mapped three-class probabilities; the comparison module calculates confidence difference. |
| xxiv. Consistency status | Working | Configurable Strong/Acceptable/Weak/Disagreement/Uncertain thresholds are evaluated using the live two-model outputs. |
| xxv. Warranty rule validation | Partial | Rule engine checks expiry, coverage, reporting period, proof, serial/model mismatch, repairs, exclusions, duplicates, and missing documents. Evidence sources are not all independently checked (for example, serial photos/repair records). |
| xxvi. Configurable policies | Working | Category policies and model-comparison thresholds are stored in policy/config files rather than scattered hard-coded rules. |
| xxvii. Serial-number verification | Partial | Receipt and warranty OCR, registered product details, serial-label photos, and repair reports are compared when OCR returns a serial. Arbitrary image OCR remains layout/quality dependent and requires review. |
| xxviii. Contradiction detection | Partial | Several chronology and product/serial inconsistencies are flagged; the full set of date/model/repair contradictions is not comprehensively covered. |
| xxix. Missing-document detection | Working | Required-document checks are policy-driven and missing documents can trigger manual review. |
| xxx. Duplicate claim detection | Working | Duplicate invoice, serial, cross-claim document hash, and high-similarity same-customer/same-category fault-description signals can raise reviewer flags. Similarity is a review signal, never an automatic rejection. |
| xxxi. Document duplicate detection | Working | SHA-256 fingerprints are recorded and reused documents can be flagged. |
| xxxii. AI-generated claim summary | Working | The assessment returns a deterministic narrative summary from persisted facts and structured supporting/opposing evidence; it does not invent facts or call an external generative service. |
| xxxiii. Claim preparation assistance | Working | Before assessment the claimant sees policy-required missing files, OCR/serial conflicts, and corrective steps. Missing-document alerts are also delivered in-app. |
| xxxiv. Final claim decision | Partial | The decision combines Python output and policy rules and routes uncertainty to manual review. The TM input is unavailable with the current labels, so the specified dual-model decision is not fully operational. |
| xxxv. Decision explanation | Working | The result presents supporting factors, warnings/opposing factors, corrective actions, policy checks, model probabilities, and version identifiers. |
| xxxvi. Manual-review workflow | Working | Reviewer queue supports approve, reject, request-more-information, and close actions; actions update status and create audit records/notifications. |
| xxxvii. Reviewer comments/override | Working | Reviewer reason and action are stored with the original automated results retained in audit history. |
| xxxviii. Claim status tracking | Working | Backend transitions are constrained to legal workflow edges; reviewer adjudication is limited to Manual Review or Additional Info Required. Requested evidence resets a claim to Submitted while preserving the prior assessment revision. |
| xxxix. Notifications and alerts | Working | Submission, status/review, repair, missing evidence, scheduled warranty expiry, reporting-window deadline, and model/anomaly notifications are persisted for the relevant owner or admin. |
| xl. Customer dashboard | Working | Live products, warranties, claim history, notifications, saved evidence inventory, missing documents, reviewer requests, and calculated reporting deadlines are available. |
| xli. Administrator dashboard | Working | Live totals, workflow state, likely outcomes, duplicates, disagreement, confidence, account access, scheduler, anomaly events, rejection reasons, fault patterns, repair/expiry trends, review frequency, model versions, and synthetic holdout metrics are shown. |
| xlii. Search/filter | Partial | Customer, reviewer, admin, and service-center queues have role-scoped search plus category/status/date and available risk/confidence/warranty filters. A unified set of every field is not exposed on every role page. |
| xliii. Data analysis/reporting | Working | Live analytics include stage/outcome/category/month, fault descriptions, reviewer rejection reasons, service-center repairs, warranty expiry months, manual-review frequency, model version counts, and labeled synthetic image-model metrics. |
| xliv. Downloadable claim report | Working | The owner and authorized staff can download a ZIP evidence bundle containing the assessment PDF (or saved assessment JSON when PDF generation failed), original evidence files, and a hash manifest. |
| xlv. Data export | Working | Admin can export claims, products, warranties, repairs, audit, and analytics as CSV, which is Excel-compatible. |
| xlvi. Data storage | Working | SQLite persists users, products, warranties, claims, repairs, prediction records, notifications, and audit events; uploaded files are held in claim directories. |
| xlvii. Audit trail | Partial | Account, role provisioning, login success/failure (failed-account identifiers are hashed), product/warranty, evidence, assessment/model version, status, reviewer, and repair events are recorded. Detailed infrastructure errors remain in server logs rather than the application audit table. |
| xlviii. Model version tracking | Working | Tabular and in-house image-model versions are stored on claim/prediction records and displayed with assessments. A Google TM version is unavailable because the supplied H5 labels are unmapped. |
| xlix. Error handling | Partial | User-facing errors are generally understandable and avoid tracebacks. Some paths still use broad catches or generic failures that hide the affected operation. |
| l. Monitoring/anomaly alerts | Working | Admins can review and acknowledge persisted alerts for repeated login failures, rejected upload types, duplicate evidence, model failures, low confidence, and model disagreements. Alert acknowledgement is audit logged. |

## Verification notes

- Updated integration suite: **17 passed** on 2026-09-27. Checks cover OCR-to-model/PDF flow, evidence bundle and revision history, evidence add/replace/remove and ownership, extended warranty entry, service-center intake and scoped queue, reviewer queue/transitions, scheduler idempotence, and admin analytics/alert acknowledgement. This is not a production load or security penetration test.
- Each dashboard page now has server-side role guards and redirects to the account’s own workspace; APIs also enforce role and record ownership. Service-center staff see only claims created by their account, while reviewers see the manual-review and information-request queue.
- The source manifest references receipt/warranty files that are not included. The new card corpus is generated from the supplied synthetic claim table; it does not invent or fabricate receipt scans.
- The Google Teachable Machine export remains unavailable/unverified. The runtime uses an explicitly named in-house visual classifier instead, so reports must not call it a Teachable Machine model or attribute its metrics to Google TM.
- The in-house visual classifier reached 90.22% on 225 held-out synthetic cards after regularization was selected on a separate validation split. This meets the numeric 85% threshold on this synthetic corpus only; it does not establish real-claim performance or Google TM performance.
- SRS non-functional targets such as 5-second dual-model latency, 10,000-claim load, 99% uptime, and 85% dual-model unseen accuracy have not been load-tested/deployment-verified.

## Remaining requirement dependencies

- The supplied Teachable Machine model labels are only `Class 1`, `Class 2`, and `Class 3`. There is no trusted mapping/export to the SRS outcomes, so the app refuses to call that model and uses the separately trained, explicitly identified in-house image model. Supplying a verified TM export/mapping is still needed to mark xxi and the strict dual-model portion of xxxiv fully Working.
- OCR of arbitrary receipt, product-label, and repair-report layouts is inherently quality/layout dependent. The UI preserves editable extracted suggestions and sends missing/contradictory fields to human review instead of claiming universal OCR accuracy.
- Deployment performance/availability targets and real-claim classifier accuracy require production data and infrastructure; the only reported image-model metric is from the held-out SRS-derived synthetic corpus.

## Shared website footer

All ten HTML pages now use the same responsive footer with AssureX branding and working Home, About, FAQs, and Support links. The final link is Sign in when logged out and changes to the signed-in user’s own workspace when authenticated. No links to missing legal or social pages were added.
