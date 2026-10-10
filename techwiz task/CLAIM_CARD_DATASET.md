# Claim-card dataset and visual model

`build_claim_card_dataset.py` uses the supplied `data/assurex_claims_full_1500(4).csv` (1,500 synthetic scenarios, 500 rows per SRS class). It maps `Class_Label` directly to the three SRS outcomes. The stratified, fixed-seed split is 70% training, 15% validation, and 15% held-out testing. All variants of a claim stay in the same split. Training uses two visually equivalent card renders per training claim; validation and testing each have one render per claim. Cards contain claim facts but never the expected class, model prediction, or decision. Source IDs are class-ordered, so cards display deterministic SHA-256 pseudonyms instead; the manifest alone retains source IDs for traceability.

Generated files are under `data/claim_card_dataset/`. `manifest.csv` maps each card to its source row, split, and outcome; `label_mapping.json` records the class mapping and split counts. This is a synthetic training corpus derived from the supplied SRS dataset. It is separate from live user claims and is never loaded into the application database.

Train and evaluate the independent image model after installing `requirements.txt`:

```powershell
.runtime\Scripts\python.exe build_claim_card_dataset.py
.runtime\Scripts\python.exe train_claim_card_model.py
```

The held-out metrics are written to `models/claim_card_model_metrics.json`. The runtime explicitly identifies this as an in-house HOG + multinomial logistic regression image model; the prior generic-label H5 file is not treated as a verified Teachable Machine model.
