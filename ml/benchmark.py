"""Compare the existing rules, baselines, and the hybrid ML coordinator."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agents import CongestionAgent, ForwardingPatternAgent, MLAgent, WirelessMobilityAgent
from baselines import LossOnlyRule, SingleAgentBaseline
from baselines.evaluator import BaselineEvaluator
from controller import Coordinator
from data import EvidenceAdapter


def _coordinator(
    adapter: EvidenceAdapter,
    use_ml: bool,
    model_path: str,
) -> Coordinator:
    tools = {
        "get_queue_evidence": adapter.get_queue_evidence,
        "get_link_evidence": adapter.get_link_evidence,
        "get_forwarding_pattern": adapter.get_forwarding_pattern,
    }
    ml_agent = MLAgent(model_path) if use_ml else None
    return Coordinator(
        agents={
            "congestion_agent": CongestionAgent(),
            "wireless_mobility_agent": WirelessMobilityAgent(),
            "forwarding_pattern_agent": ForwardingPatternAgent(),
        },
        evidence_tools=tools,
        evidence_index=adapter.get_evidence_index(),
        ml_agent=ml_agent,
    )


def benchmark(
    dataset_dir: str | Path = "Monitoring-Dataset",
    split: str = "medium_test_sft.jsonl",
    model_path: str = "artifacts/ml/random_forest.joblib",
    logistic_model_path: str = "artifacts/ml/logistic_regression.joblib",
    output_path: str | Path = "artifacts/ml/baseline_vs_hybrid.json",
    limit: int | None = None,
) -> dict[str, Any]:
    adapter = EvidenceAdapter(dataset_dir=str(dataset_dir))
    adapter.load_split(split)
    cases = [adapter.get_case(case_id) for case_id in adapter.list_case_ids()]
    cases = [case for case in cases if case is not None]
    if limit is not None:
        cases = cases[:limit]

    truth_rows = [{"true_behavior": (case.ground_truth or {}).get("true_behavior")} for case in cases]
    predictions: dict[str, list[str]] = {
        "loss_only": [],
        "single_agent": [],
        "rules": [],
        "hybrid_random_forest": [],
        "hybrid_logistic_regression": [],
    }
    timings: dict[str, float] = {}

    started = time.perf_counter()
    loss_rule = LossOnlyRule(threshold=0.3)
    for case in cases:
        predictions["loss_only"].append(loss_rule.diagnose(case.case_id, case.raw_sources).primary)
    timings["loss_only"] = time.perf_counter() - started

    started = time.perf_counter()
    single_agent = SingleAgentBaseline()
    for case in cases:
        predictions["single_agent"].append(
            single_agent.diagnose(case.case_id, case.raw_sources).primary
        )
    timings["single_agent"] = time.perf_counter() - started

    started = time.perf_counter()
    rule_coordinator = _coordinator(adapter, False, model_path)
    for case in cases:
        predictions["rules"].append(
            rule_coordinator.diagnose(
                case.case_id, case.monitored_node, case.window, case.raw_sources
            ).decision.primary
        )
    timings["rules"] = time.perf_counter() - started

    for method_name, learned_model_path in (
        ("hybrid_random_forest", model_path),
        ("hybrid_logistic_regression", logistic_model_path),
    ):
        started = time.perf_counter()
        hybrid_coordinator = _coordinator(adapter, True, learned_model_path)
        for case in cases:
            predictions[method_name].append(
                hybrid_coordinator.diagnose(
                    case.case_id, case.monitored_node, case.window, case.raw_sources
                ).decision.primary
            )
        timings[method_name] = time.perf_counter() - started

    report: dict[str, Any] = {
        "config": {
            "split": split,
            "cases": len(cases),
            "model_path": model_path,
            "logistic_model_path": logistic_model_path,
        },
        "methods": {},
        "elapsed_seconds": timings,
    }
    for method_name, method_predictions in predictions.items():
        result = BaselineEvaluator().evaluate(method_name, truth_rows, method_predictions)
        report["methods"][method_name] = asdict(result)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", default="Monitoring-Dataset")
    parser.add_argument("--split", default="medium_test_sft.jsonl")
    parser.add_argument("--model-path", default="artifacts/ml/random_forest.joblib")
    parser.add_argument(
        "--logistic-model-path",
        default="artifacts/ml/logistic_regression.joblib",
    )
    parser.add_argument("--output-path", default="artifacts/ml/baseline_vs_hybrid.json")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    report = benchmark(**vars(args))
    for method, metrics in report["methods"].items():
        print(
            method,
            "FAR=%.3f MDR=%.3f coverage=%.3f abstention=%.3f macro_f1=%.3f"
            % (
                metrics["false_accusation_rate"],
                metrics["malicious_detection_rate"],
                metrics["coverage"],
                metrics["abstention_rate"],
                metrics["macro_f1"],
            ),
        )


if __name__ == "__main__":
    main()
