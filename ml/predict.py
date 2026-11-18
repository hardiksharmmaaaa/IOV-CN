"""Inference wrapper for trained IoV diagnosis models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import joblib

from .dataset import LABELS
from .features import FEATURE_NAMES, extract_features


MALICIOUS_LABELS = {"malicious_blackhole", "malicious_selective_forwarding"}
UNCERTAIN_LABEL = "uncertain_needs_more_evidence"


@dataclass(frozen=True)
class MLPrediction:
    model_name: str
    predicted_label: str
    primary: str
    confidence: float
    abstained: bool
    threshold: float
    probabilities: dict[str, float]
    top_features: list[dict[str, float | str]]


def _primary_from_label(label: str) -> str:
    if label in MALICIOUS_LABELS:
        return "suspected_malicious"
    if label == UNCERTAIN_LABEL:
        return "insufficient_evidence"
    return "benign"


def _classifier(model: Any) -> Any:
    if hasattr(model, "coef_"):
        return model
    if hasattr(model, "named_steps") and "classifier" in model.named_steps:
        return model.named_steps["classifier"]
    return None


def _top_features(
    artifact: Mapping[str, Any],
    predicted_label: str,
    values: tuple[float, ...],
) -> list[dict[str, float | str]]:
    model = artifact["model"]
    names = list(artifact["feature_names"])
    classifier = _classifier(model)
    scores: list[float]

    if hasattr(model, "feature_importances_"):
        importances = list(model.feature_importances_)
        scores = [float(value) for value in importances]
    elif classifier is not None and hasattr(classifier, "coef_"):
        classes = list(classifier.classes_)
        class_index = classes.index(predicted_label)
        scores = [abs(float(value)) for value in classifier.coef_[class_index]]
    else:
        scores = [0.0] * len(names)

    ranked = sorted(range(len(names)), key=lambda index: scores[index], reverse=True)
    return [
        {
            "feature": names[index],
            "importance": scores[index],
            "value": float(values[index]),
        }
        for index in ranked[:8]
    ]


class MLModel:
    """Load one trained artifact and produce safe, structured predictions."""

    def __init__(self, artifact_path: str | Path):
        path = Path(artifact_path)
        if not path.exists():
            raise FileNotFoundError(f"ML artifact not found: {path}")
        artifact = joblib.load(path)
        if tuple(artifact.get("feature_names", ())) != tuple(FEATURE_NAMES):
            raise ValueError("Artifact feature contract does not match current code")
        if tuple(artifact.get("labels", ())) != tuple(LABELS):
            raise ValueError("Artifact label contract does not match current code")
        self.artifact = artifact
        self.artifact_path = path

    @property
    def model_name(self) -> str:
        return str(self.artifact["model_name"])

    @property
    def threshold(self) -> float:
        return float(self.artifact["confidence_threshold"])

    def predict(self, raw_sources: Mapping[str, Any]) -> MLPrediction:
        vector = extract_features(raw_sources)
        model = self.artifact["model"]
        probabilities_array = model.predict_proba([list(vector.values)])[0]
        classes = list(model.classes_) if hasattr(model, "classes_") else list(
            model.named_steps["classifier"].classes_
        )
        probabilities = {
            str(label): float(probability)
            for label, probability in zip(classes, probabilities_array)
        }
        predicted_label = max(probabilities, key=probabilities.get)
        confidence = probabilities[predicted_label]
        abstained = confidence < self.threshold or predicted_label == UNCERTAIN_LABEL
        primary = "insufficient_evidence" if abstained else _primary_from_label(predicted_label)
        return MLPrediction(
            model_name=self.model_name,
            predicted_label=predicted_label,
            primary=primary,
            confidence=confidence,
            abstained=abstained,
            threshold=self.threshold,
            probabilities=probabilities,
            top_features=_top_features(self.artifact, predicted_label, vector.values),
        )
