"""AssureX independent claim-card image classifier (HOG + logistic regression).

The previous bundled file had generic, unmapped labels. It is deliberately not
used. Train this classifier from the generated, leakage-safe card corpus with
train_claim_card_model.py. This is an in-house image model, not a Google TM export.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
from PIL import Image, ImageOps
from skimage.feature import hog

BASE_DIR = Path(__file__).resolve().parent
CLASS_NAMES = ["Valid Claim", "Invalid Claim", "Manual Review"]
IMAGE_SIZE = (96, 72)


def image_features(path: Path) -> np.ndarray:
    with Image.open(path) as source:
        image = ImageOps.fit(source.convert("L"), IMAGE_SIZE, Image.Resampling.LANCZOS)
        pixels = np.asarray(image, dtype=np.uint8)
    return hog(pixels, orientations=9, pixels_per_cell=(8, 8), cells_per_block=(2, 2),
               block_norm="L2-Hys", transform_sqrt=True, feature_vector=True)


def read_labels(path: Path) -> list[str]:
    labels = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if labels != CLASS_NAMES:
        raise ValueError("Image-model labels are not mapped to the verified SRS class order.")
    return labels


def predict(model_path: Path, labels_path: Path, card_path: Path) -> dict:
    labels = read_labels(labels_path)
    if not model_path.exists():
        raise FileNotFoundError(f"Trained claim-card image model missing: {model_path}")
    model = joblib.load(model_path)
    probabilities = np.asarray(model.predict_proba(image_features(card_path)[None, :])[0], dtype=float)
    if probabilities.shape != (len(labels),) or not np.isfinite(probabilities).all() or not np.isclose(probabilities.sum(), 1, atol=0.01):
        raise ValueError("Image model returned invalid probabilities.")
    scores = {name: float(probability) for name, probability in zip(labels, probabilities)}
    top = max(scores, key=scores.get)
    version = hashlib.sha256(model_path.read_bytes()).hexdigest()[:16]
    return {"prediction": top, "top_class": top, "confidence": scores[top],
            "confidences": scores, "model": model_path.name, "model_type": "HOG + multinomial logistic regression",
            "model_version": version}


def main() -> None:
    parser = argparse.ArgumentParser(description="AssureX claim-card image inference")
    parser.add_argument("--model", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--card", required=True)
    parser.add_argument("--claim-id", default="")
    parser.add_argument("--out", default=str(BASE_DIR / "outputs" / "step06_image_prediction.json"))
    args = parser.parse_args()
    result = predict(Path(args.model), Path(args.labels), Path(args.card))
    result.update(claim_id=args.claim_id, source_card=args.card)
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
