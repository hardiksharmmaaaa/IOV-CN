"""Learned evidence agent for the hybrid IoV diagnosis pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ml.predict import MLModel, MLPrediction


@dataclass
class MLFinding:
    candidate_cause: str
    supporting_record_ids: list[str] = field(default_factory=list)
    counterevidence_ids: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    justification: str = ""
    confidence: str = "low"
    tool_calls_used: int = 0
    model_name: str = ""
    predicted_label: str = ""
    probability: float = 0.0
    probabilities: dict[str, float] = field(default_factory=dict)
    top_features: list[dict[str, Any]] = field(default_factory=list)


class MLAgent:
    """Run a trained model while preserving evidence-citation constraints."""

    name = "ml_agent"
    role = "Provide a learned behavior estimate from leakage-safe telemetry features."
    max_tool_calls = 2

    def __init__(self, artifact_path: str):
        self.model = MLModel(artifact_path)
        self.findings: list[MLFinding] = []

    def investigate(
        self,
        case_id: str,
        raw_sources: dict[str, Any],
        available_tools: dict[str, Any],
    ) -> MLFinding:
        prediction = self.model.predict(raw_sources)
        supporting_ids = self._supporting_ids(
            case_id,
            prediction,
            available_tools,
        )
        if prediction.abstained:
            candidate = "insufficient_evidence"
            confidence = "low"
            justification = (
                "The trained model did not reach its validation-selected confidence "
                "threshold, so the learned component abstains."
            )
        else:
            candidate = prediction.predicted_label
            confidence = self._confidence_level(prediction.confidence)
            features = ", ".join(
                item["feature"] for item in prediction.top_features[:3]
            )
            justification = (
                f"The trained {prediction.model_name} model predicts "
                f"{prediction.predicted_label}; strongest model features include {features}."
            )

        finding = MLFinding(
            candidate_cause=candidate,
            supporting_record_ids=supporting_ids,
            justification=justification,
            confidence=confidence,
            tool_calls_used=min(2, len(self._tool_names(prediction))),
            model_name=prediction.model_name,
            predicted_label=prediction.predicted_label,
            probability=prediction.confidence,
            probabilities=prediction.probabilities,
            top_features=prediction.top_features,
        )
        self.findings.append(finding)
        return finding

    @staticmethod
    def _confidence_level(probability: float) -> str:
        if probability >= 0.85:
            return "high"
        if probability >= 0.65:
            return "medium"
        return "low"

    @staticmethod
    def _tool_names(prediction: MLPrediction) -> list[str]:
        if prediction.predicted_label in {
            "honest_congestion_full_queue",
        }:
            return ["get_queue_evidence", "get_forwarding_pattern"]
        if prediction.predicted_label == "honest_link_degradation":
            return ["get_link_evidence", "get_forwarding_pattern"]
        return ["get_forwarding_pattern", "get_link_evidence"]

    def _supporting_ids(
        self,
        case_id: str,
        prediction: MLPrediction,
        available_tools: dict[str, Any],
    ) -> list[str]:
        ids: list[str] = []
        for tool_name in self._tool_names(prediction):
            tool = available_tools.get(tool_name)
            if tool is None:
                continue
            try:
                records = tool(case_id=case_id)
            except Exception:
                records = []
            if not isinstance(records, list):
                records = [records] if records else []
            ids.extend(
                record.get("record_id")
                for record in records
                if isinstance(record, dict)
                and record.get("case_id") == case_id
                and record.get("record_id")
            )
        return list(dict.fromkeys(ids))
