"""Train and honestly evaluate the independent visual claim-card model."""
from __future__ import annotations

import csv
import json
import importlib
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "claim_card_dataset"
MODEL = ROOT / "models" / "claim_card_hog.joblib"
LABELS = ["Valid Claim", "Invalid Claim", "Manual Review"]


def read_manifest(split: str) -> tuple[list[Path], list[str]]:
    paths, targets = [], []
    with (DATA / "manifest.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["split"] == split:
                paths.append(DATA / row["image"])
                targets.append(row["label"])
    return paths, targets


def main() -> None:
    inference = importlib.import_module("06b_teachable_machine_inference")
    train_paths, y_train = read_manifest("training")
    validation_paths, y_validation = read_manifest("validation")
    test_paths, y_test = read_manifest("testing")
    if not train_paths or not validation_paths or not test_paths:
        raise SystemExit("Build the claim-card dataset before training.")
    x_train = np.vstack([inference.image_features(path) for path in train_paths])
    x_validation = np.vstack([inference.image_features(path) for path in validation_paths])
    x_test = np.vstack([inference.image_features(path) for path in test_paths])
    candidates = []
    for regularization in (0.01, 0.1, 1.0, 10.0, 100.0):
        candidate = LogisticRegression(C=regularization, solver="lbfgs", max_iter=1000,
                                       class_weight="balanced", random_state=42)
        candidate.fit(x_train, y_train)
        candidate_predictions = candidate.predict(x_validation)
        candidates.append((f1_score(y_validation, candidate_predictions, labels=LABELS, average="macro"),
                           accuracy_score(y_validation, candidate_predictions), regularization))
    _, validation_accuracy, best_c = max(candidates, key=lambda item: (item[0], item[1], -item[2]))
    model = LogisticRegression(C=best_c, solver="lbfgs", max_iter=1000,
                               class_weight="balanced", random_state=42)
    model.fit(np.vstack((x_train, x_validation)), y_train + y_validation)
    predictions = model.predict(x_test)
    metrics = {"training_images": len(y_train), "validation_images": len(y_validation),
               "training_plus_validation_fit_images": len(y_train) + len(y_validation),
               "selected_regularization_C": best_c, "validation_accuracy": float(validation_accuracy),
               "held_out_test_images": len(y_test),
               "accuracy": float(accuracy_score(y_test, predictions)),
               "classes": LABELS,
               "classification_report": classification_report(y_test, predictions, labels=LABELS, output_dict=True, zero_division=0),
               "confusion_matrix_rows_actual_columns_predicted": confusion_matrix(y_test, predictions, labels=LABELS).tolist(),
               "test_split": "pre-separated by claim; no training claim occurs in test",
               "leakage_control": "source claim IDs are hashed before rendering; class, prediction, and outcome are not rendered",
               "visual_features": f"HOG, {inference.IMAGE_SIZE[0]}x{inference.IMAGE_SIZE[1]} grayscale",
               "model": "Multinomial logistic regression on HOG image features"}
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL)
    (MODEL.parent / "claim_card_labels.txt").write_text("\n".join(LABELS) + "\n", encoding="utf-8")
    (MODEL.parent / "claim_card_model_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps({"accuracy": metrics["accuracy"], "held_out_test_images": len(y_test),
                      "confusion_matrix_rows_actual_columns_predicted": metrics["confusion_matrix_rows_actual_columns_predicted"],
                      "metrics_path": str((MODEL.parent / "claim_card_model_metrics.json").resolve())}, indent=2))


if __name__ == "__main__":
    main()
