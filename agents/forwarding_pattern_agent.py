"""Forwarding-pattern specialist agent.

Examines matched receive/forward events, loss sequences, flow patterns, and
neighboring windows to identify persistent or selective failures requiring
further examination.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ForwardingPatternFinding:
    candidate_cause: str
    supporting_record_ids: list[str] = field(default_factory=list)
    counterevidence_ids: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    justification: str = ""
    confidence: str = "low"
    tool_calls_used: int = 0


class ForwardingPatternAgent:
    """Specialist agent for forwarding-pattern evidence."""

    name = "forwarding_pattern_agent"
    role = "Identify persistent or selective failures that require further examination."

    evidence_tools = [
        "get_forwarding_pattern",
        "get_link_evidence",
    ]

    max_tool_calls = 2

    def __init__(self) -> None:
        self.findings: list[ForwardingPatternFinding] = []

    def investigate(
        self,
        case_id: str,
        raw_sources: dict[str, Any],
        available_tools: dict[str, Any],
    ) -> ForwardingPatternFinding:
        """Run forwarding-pattern investigation on a relay case."""
        finding = ForwardingPatternFinding(
            candidate_cause="unknown",
            confidence="low",
        )

        pattern_records = self._call_tool(
            available_tools,
            "get_forwarding_pattern",
            case_id=case_id,
        )
        finding.tool_calls_used += 1

        link_records = self._call_tool(
            available_tools,
            "get_link_evidence",
            case_id=case_id,
        )
        finding.tool_calls_used += 1

        finding.supporting_record_ids = [
            r.get("record_id") for r in pattern_records if r.get("case_id") == case_id
        ]
        finding.supporting_record_ids += [
            r.get("record_id") for r in link_records if r.get("case_id") == case_id
        ]

        received = sum(r.get("packets_received", 0) for r in pattern_records)
        forwarded = sum(r.get("packets_forwarded", 0) for r in pattern_records)
        loss_ratio = 1 - (forwarded / received) if received > 0 else 0

        selective = any(
            r.get("selective_drop_indicator", False) for r in pattern_records
        )
        persistent_loss = loss_ratio > 0.5 and received > 10

        if selective:
            finding.candidate_cause = "malicious_selective_forwarding"
            finding.confidence = "high"
            finding.justification = (
                "Selective drop indicators detected in forwarding patterns; "
                "relay forwards only a subset of received traffic."
            )
        elif persistent_loss:
            finding.candidate_cause = "malicious_blackhole"
            finding.confidence = "high"
            finding.justification = (
                "Persistent high loss ratio with adequate received volume; "
                "consistent with blackhole-like behavior."
            )
        else:
            finding.candidate_cause = "insufficient_evidence"
            finding.confidence = "low"
            finding.justification = (
                "No persistent or selective failure pattern detected."
            )
            if not pattern_records:
                finding.missing_fields.append("forwarding_pattern")

        self.findings.append(finding)
        return finding

    def _call_tool(
        self,
        available_tools: dict[str, Any],
        tool_name: str,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        tool = available_tools.get(tool_name)
        if tool is None:
            return []
        try:
            result = tool(**kwargs)
            if isinstance(result, list):
                return result
            return [result] if result else []
        except Exception:
            return []

    def revise(
        self,
        case_id: str,
        counterevidence: list[dict[str, Any]],
        raw_sources: dict[str, Any],
        available_tools: dict[str, Any],
    ) -> ForwardingPatternFinding:
        """Single revision round after challenge. Allows one additional tool call."""
        finding = ForwardingPatternFinding(
            candidate_cause="unknown",
            confidence="low",
        )

        finding.counterevidence_ids = [
            r.get("record_id") for r in counterevidence if r.get("case_id") == case_id
        ]

        extra = self._call_tool(
            available_tools,
            "get_forwarding_pattern",
            case_id=case_id,
            include_counterevidence=True,
        )
        finding.tool_calls_used = 1

        received = sum(r.get("packets_received", 0) for r in extra)
        forwarded = sum(r.get("packets_forwarded", 0) for r in extra)
        loss_ratio = 1 - (forwarded / received) if received > 0 else 0
        selective = any(
            r.get("selective_drop_indicator", False) for r in extra
        )

        if selective:
            finding.candidate_cause = "malicious_selective_forwarding"
            finding.confidence = "high"
            finding.justification = (
                "Counterevidence reviewed; selective drop indicators persist."
            )
        elif loss_ratio > 0.5:
            finding.candidate_cause = "malicious_blackhole"
            finding.confidence = "high"
            finding.justification = (
                "Counterevidence reviewed; persistent high loss ratio persists."
            )
        else:
            finding.candidate_cause = "insufficient_evidence"
            finding.confidence = "low"
            finding.justification = (
                "Counterevidence and re-check did not support malicious pattern; "
                "abstaining."
            )

        self.findings.append(finding)
        return finding
