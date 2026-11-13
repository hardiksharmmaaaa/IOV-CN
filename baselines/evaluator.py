"""Baseline evaluator.

Compares three approaches on the same cases:
1. Loss-only threshold rule
2. Single AI agent baseline
3. Proposed specialist-agent system (Coordinator)

Reports metrics: false accusation rate, malicious detection rate, coverage,
abstention, precision, macro F1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvaluationResult:
    method_name: str
    total_cases: int
    false_accusation_rate: float  # benign -> suspected_malicious
    malicious_detection_rate: float  # malicious -> suspected_malicious
    coverage: float  # fraction with benign or suspected_malicious decision
    abstention_rate: float
    precision_malicious: float
    macro_f1: float
    confusion_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    abstention_by_class: dict[str, int] = field(default_factory=dict)


class BaselineEvaluator:
    """Runs all methods on the same case set and computes comparable metrics."""

    def __init__(self) -> None:
        self.results: list[EvaluationResult] = []

    def evaluate(
        self,
        method_name: str,
        cases: list[dict[str, Any]],
        predictions: list[str],
    ) -> EvaluationResult:
        """Evaluate one method against ground truth.

        cases: list of dicts with 'true_behavior' key
        predictions: list of predicted primary decisions matching cases order
        """
        total = len(cases)

        # Count per class
        true_benign = 0
        true_malicious = 0
        true_uncertain = 0

        # Decision mapping for metrics
        # We treat 'suspected_malicious' as positive for malicious detection
        tp = 0  # malicious correctly detected
        fp = 0  # benign falsely accused
        fn = 0  # malicious missed
        tn = 0  # benign correctly not accused

        abstention_by_class: dict[str, int] = {}

        decided_cases = 0
        correct_decided = 0
        per_class_correct: dict[str, int] = {}
        per_class_total: dict[str, int] = {}

        for case, pred in zip(cases, predictions):
            true_label = case.get("true_behavior", "uncertain_needs_more_evidence")

            # Group true labels
            if true_label in ("honest_normal", "honest_congestion_full_queue", "honest_link_degradation"):
                true_group = "benign"
                true_benign += 1
            elif true_label in ("malicious_blackhole", "malicious_selective_forwarding"):
                true_group = "malicious"
                true_malicious += 1
            else:
                true_group = "uncertain"
                true_uncertain += 1

            per_class_total[true_label] = per_class_total.get(true_label, 0) + 1

            if pred == "insufficient_evidence":
                abstention_by_class[true_label] = abstention_by_class.get(true_label, 0) + 1
                continue

            decided_cases += 1

            if true_group == "benign" and pred == "suspected_malicious":
                fp += 1
            elif true_group == "malicious" and pred == "suspected_malicious":
                tp += 1
            elif true_group == "benign" and pred == "benign":
                tn += 1
            elif true_group == "malicious" and pred == "benign":
                fn += 1

            if pred == true_label or (
                (true_group == "benign" and pred == "benign")
                or (true_group == "malicious" and pred == "suspected_malicious")
            ):
                correct_decided += 1
                per_class_correct[true_label] = per_class_correct.get(true_label, 0) + 1

        false_accusation_rate = fp / true_benign if true_benign > 0 else 0.0
        malicious_detection_rate = tp / true_malicious if true_malicious > 0 else 0.0
        coverage = decided_cases / total if total > 0 else 0.0
        abstention_rate = (total - decided_cases) / total if total > 0 else 0.0
        precision_malicious = tp / (tp + fp) if (tp + fp) > 0 else 0.0

        # Macro F1 across benign and malicious classes (decided cases only)
        recall_benign = tn / (tn + fp) if (tn + fp) > 0 else 0.0
        recall_malicious = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        precision_benign = tn / (tn + fn) if (tn + fn) > 0 else 0.0

        f1_benign = (
            2 * precision_benign * recall_benign / (precision_benign + recall_benign)
            if (precision_benign + recall_benign) > 0 else 0.0
        )
        f1_malicious = (
            2 * precision_malicious * recall_malicious / (precision_malicious + recall_malicious)
            if (precision_malicious + recall_malicious) > 0 else 0.0
        )
        macro_f1 = (f1_benign + f1_malicious) / 2

        result = EvaluationResult(
            method_name=method_name,
            total_cases=total,
            false_accusation_rate=false_accusation_rate,
            malicious_detection_rate=malicious_detection_rate,
            coverage=coverage,
            abstention_rate=abstention_rate,
            precision_malicious=precision_malicious,
            macro_f1=macro_f1,
            confusion_counts={
                "benign": {"true_benign": true_benign, "false_positive": fp, "true_negative": tn},
                "malicious": {"true_malicious": true_malicious, "true_positive": tp, "false_negative": fn},
            },
            abstention_by_class=abstention_by_class,
        )
        self.results.append(result)
        return result

    def compare_all(self) -> dict[str, EvaluationResult]:
        return {r.method_name: r for r in self.results}

    def summary_table(self) -> str:
        lines = [
            f"{'Method':<25} {'FAR':>6} {'MDR':>6} {'Cov':>6} {'Abs':>6} {'Prec':>6} {'F1':>6}",
            "-" * 70,
        ]
        for r in self.results:
            lines.append(
                f"{r.method_name:<25} "
                f"{r.false_accusation_rate:>6.3f} "
                f"{r.malicious_detection_rate:>6.3f} "
                f"{r.coverage:>6.3f} "
                f"{r.abstention_rate:>6.3f} "
                f"{r.precision_malicious:>6.3f} "
                f"{r.macro_f1:>6.3f}"
            )
        return "\n".join(lines)
