"""Train and compare the IoV Random Forest and Logistic Regression models.

Usage::

    .venv/bin/python -m ml.train

The training split is used only for fitting. The validation split selects the
confidence threshold for abstention. The test split is evaluated only after
that threshold is frozen.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from baselines.evaluator import BaselineEvaluator

from .dataset import LABELS, LabeledCase, load_jsonl_cases
from .features import FEATURE_NAMES, extract_features


DEFAULT_SEED = 42
DEFAULT_MIN_COVERAGE = 0.70
DEFAULT_THRESHOLD_GRID = tuple(round(0.50 + index * 0.025, 3) for index in range(19))


def _matrix(cases: Iterable[LabeledCase]) -> tuple[list[list[float]], list[str]]:
    features: list[list[float]] = []
    labels: list[str] = []
    for case in cases:
        vector = extract_features(case.raw_sources)
        if vector.names != tuple(FEATURE_NAMES):
            raise ValueError("Feature order does not match the model contract")
        features.append(list(vector.values))
        labels.append(case.label)
    return features, labels


def _primary_from_label(label: str) -> str:
    if label in {"malicious_blackhole", "malicious_selective_forwarding"}:
        return "suspected_malicious"
    if label == "uncertain_needs_more_evidence":
        return "insufficient_evidence"
    return "benign"


def _decisions(model: Any, features: list[list[float]], threshold: float) -> list[str]:
    probabilities = model.predict_proba(features)
    classes = getattr(model, "classes_", None)
    if classes is None and hasattr(model, "named_steps"):
        classes = model.named_steps["classifier"].classes_
    if classes is None:
        raise AttributeError("Model does not expose class labels")
    classes = list(classes)
    decisions: list[str] = []
    for row in probabilities:
        best_index = max(range(len(row)), key=row.__getitem__)
        best_probability = float(row[best_index])
        predicted_label = str(classes[best_index])
        if best_probability < threshold:
            decisions.append("insufficient_evidence")
        else:
            decisions.append(_primary_from_label(predicted_label))
    return decisions


def _evaluate(
    method_name: str,
    cases: list[LabeledCase],
    predictions: list[str],
) -> dict[str, Any]:
    case_rows = [{"true_behavior": case.label} for case in cases]
    result = BaselineEvaluator().evaluate(method_name, case_rows, predictions)
    return asdict(result)


def _select_threshold(
    model: Any,
    validation_features: list[list[float]],
    validation_cases: list[LabeledCase],
    max_false_accusation_rate: float,
    min_coverage: float,
) -> tuple[float, dict[str, Any], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    for threshold in DEFAULT_THRESHOLD_GRID:
        predictions = _decisions(model, validation_features, threshold)
        metrics = _evaluate("validation", validation_cases, predictions)
        candidates.append({"threshold": threshold, "metrics": metrics})

    eligible = [
        item
        for item in candidates
        if item["metrics"]["false_accusation_rate"] <= max_false_accusation_rate
        and item["metrics"]["coverage"] >= min_coverage
    ]
    pool = eligible or candidates
    selected = max(
        pool,
        key=lambda item: (
            item["metrics"]["macro_f1"],
            item["metrics"]["malicious_detection_rate"],
            item["metrics"]["coverage"],
            -item["threshold"],
        ),
    )
    return selected["threshold"], selected["metrics"], candidates


def _build_models(seed: int) -> dict[str, Any]:
    return {
        "random_forest": RandomForestClassifier(
            n_estimators=150,
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            random_state=seed,
            n_jobs=-1,
        ),
        "logistic_regression": Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        max_iter=2000,
                        class_weight="balanced",
                        random_state=seed,
                    ),
                ),
            ]
        ),
    }


def train_and_evaluate(
    dataset_dir: str | Path = "Monitoring-Dataset",
    output_dir: str | Path = "artifacts/ml",
    train_split: str = "medium_train_sft.jsonl",
    validation_split: str = "medium_validation_sft.jsonl",
    test_split: str = "medium_test_sft.jsonl",
    seed: int = DEFAULT_SEED,
    max_false_accusation_rate: float = 0.05,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> dict[str, Any]:
    """Fit both models and return a JSON-serializable comparison report."""
    dataset_path = Path(dataset_dir)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    train_cases = load_jsonl_cases(dataset_path / train_split)
    validation_cases = load_jsonl_cases(dataset_path / validation_split)
    test_cases = load_jsonl_cases(dataset_path / test_split)
    train_x, train_y = _matrix(train_cases)
    validation_x, _ = _matrix(validation_cases)
    test_x, _ = _matrix(test_cases)

    report: dict[str, Any] = {
        "config": {
            "seed": seed,
            "train_split": train_split,
            "validation_split": validation_split,
            "test_split": test_split,
            "feature_count": len(FEATURE_NAMES),
            "labels": list(LABELS),
            "max_false_accusation_rate_for_threshold_selection": max_false_accusation_rate,
            "min_coverage_for_threshold_selection": min_coverage,
        },
        "models": {},
    }

    for model_name, model in _build_models(seed).items():
        model.fit(train_x, train_y)
        threshold, validation_metrics, threshold_candidates = _select_threshold(
            model,
            validation_x,
            validation_cases,
            max_false_accusation_rate,
            min_coverage,
        )
        test_predictions = _decisions(model, test_x, threshold)
        test_metrics = _evaluate(model_name, test_cases, test_predictions)

        artifact = {
            "model": model,
            "model_name": model_name,
            "feature_names": list(FEATURE_NAMES),
            "labels": list(LABELS),
            "confidence_threshold": threshold,
            "seed": seed,
        }
        artifact_path = destination / f"{model_name}.joblib"
        joblib.dump(artifact, artifact_path)

        report["models"][model_name] = {
            "artifact": str(artifact_path),
            "confidence_threshold": threshold,
            "validation_metrics": validation_metrics,
            "test_metrics": test_metrics,
            "threshold_candidates": threshold_candidates,
        }

    report_path = destination / "model_comparison.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", default="Monitoring-Dataset")
    parser.add_argument("--output-dir", default="artifacts/ml")
    parser.add_argument("--train-split", default="medium_train_sft.jsonl")
    parser.add_argument("--validation-split", default="medium_validation_sft.jsonl")
    parser.add_argument("--test-split", default="medium_test_sft.jsonl")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--max-far", type=float, default=0.05)
    parser.add_argument("--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE)
    args = parser.parse_args()

    report = train_and_evaluate(
        dataset_dir=args.dataset_dir,
        output_dir=args.output_dir,
        train_split=args.train_split,
        validation_split=args.validation_split,
        test_split=args.test_split,
        seed=args.seed,
        max_false_accusation_rate=args.max_far,
        min_coverage=args.min_coverage,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
