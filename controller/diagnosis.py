"""Diagnosis result dataclasses for the coordinator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Decision:
    primary: str  # "benign" | "suspected_malicious" | "insufficient_evidence"
    secondary_cause: str | None = None
    supporting_record_ids: list[str] = field(default_factory=list)
    contradictory_evidence: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)
    rule_applied: str = ""
    confidence: str = "low"


@dataclass
class DiagnosisResult:
    case_id: str
    monitored_node: str
    window: dict[str, Any] = field(default_factory=dict)
    decision: Decision = field(default_factory=lambda: Decision(primary="insufficient_evidence"))
    agent_findings: dict[str, Any] = field(default_factory=dict)
    challenge_rounds: int = 0
    trace: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "monitored_node": self.monitored_node,
            "window": self.window,
            "decision": {
                "primary": self.decision.primary,
                "secondary_cause": self.decision.secondary_cause,
                "supporting_record_ids": self.decision.supporting_record_ids,
                "contradictory_evidence": self.decision.contradictory_evidence,
                "missing_info": self.decision.missing_info,
                "rule_applied": self.decision.rule_applied,
                "confidence": self.decision.confidence,
            },
            "agent_findings": self.agent_findings,
            "challenge_rounds": self.challenge_rounds,
            "trace": self.trace,
        }
