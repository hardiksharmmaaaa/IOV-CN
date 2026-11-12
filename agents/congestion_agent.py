"""Congestion specialist agent.

Examines queue occupancy, queue-drop events, offered load, and forwarding delay
to determine whether congestion or overflow explains observed packet losses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CongestionFinding:
    candidate_cause: str
    supporting_record_ids: list[str] = field(default_factory=list)
    counterevidence_ids: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    justification: str = ""
    confidence: str = "low"
    tool_calls_used: int = 0


class CongestionAgent:
    """Specialist agent for congestion and queue evidence."""

    name = "congestion_agent"
    role = "Determine whether congestion or overflow explains observed losses."

    evidence_tools = [
        "get_queue_evidence",
        "get_forwarding_pattern",
    ]

    max_tool_calls = 2

    def __init__(self) -> None:
        self.findings: list[CongestionFinding] = []

    def investigate(
        self,
        case_id: str,
        raw_sources: dict[str, Any],
        available_tools: dict[str, Any],
    ) -> CongestionFinding:
        """Run congestion investigation on a relay case.

        Returns a structured CongestionFinding. Makes at most max_tool_calls
        read-only evidence lookups before forming a hypothesis.
        """
        finding = CongestionFinding(
            candidate_cause="unknown",
            confidence="low",
        )

        # First pass: inspect queue and forwarding pattern evidence
        queue_records = self._call_tool(
            available_tools,
            "get_queue_evidence",
            case_id=case_id,
        )
        finding.tool_calls_used += 1

        pattern_records = self._call_tool(
            available_tools,
            "get_forwarding_pattern",
            case_id=case_id,
        )
        finding.tool_calls_used += 1

        # Validate cited records belong to this case
        finding.supporting_record_ids = [
            r.get("record_id") for r in queue_records if r.get("case_id") == case_id
        ]
        finding.supporting_record_ids += [
            r.get("record_id") for r in pattern_records if r.get("case_id") == case_id
        ]

        # Form hypothesis from evidence
        queue_full = any(
            r.get("queue_occupancy_pct", 0) >= 90 for r in queue_records
        )
        queue_drops = any(
            r.get("queue_drop_events", 0) > 0 for r in queue_records
        )
        high_delay = any(
            r.get("avg_forwarding_delay_ms", 0) > 100 for r in pattern_records
        )

        if queue_full or queue_drops or high_delay:
            finding.candidate_cause = "honest_congestion_full_queue"
            finding.confidence = "medium"
            finding.justification = (
                "Queue occupancy, queue-drop events, or elevated forwarding delay "
                "align with observed packet losses, indicating benign congestion."
            )
        else:
            finding.candidate_cause = "insufficient_evidence"
            finding.confidence = "low"
            finding.justification = (
                "No queue, drop, or delay evidence supports congestion as the cause."
            )
            if not queue_records:
                finding.missing_fields.append("queue_evidence")
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
        """Invoke a read-only evidence tool if available."""
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
    ) -> CongestionFinding:
        """Single revision round after challenge. Allows one additional tool call."""
        finding = CongestionFinding(
            candidate_cause="unknown",
            confidence="low",
        )

        # Incorporate counterevidence IDs
        finding.counterevidence_ids = [
            r.get("record_id") for r in counterevidence if r.get("case_id") == case_id
        ]

        # One additional tool call permitted in revision
        extra = self._call_tool(
            available_tools,
            "get_queue_evidence",
            case_id=case_id,
            include_counterevidence=True,
        )
        finding.tool_calls_used = 1

        queue_full = any(
            r.get("queue_occupancy_pct", 0) >= 90 for r in extra
        )
        if queue_full:
            finding.candidate_cause = "honest_congestion_full_queue"
            finding.confidence = "medium"
            finding.justification = (
                "After reviewing counterevidence, queue occupancy still indicates "
                "congestion as a plausible benign cause."
            )
        else:
            finding.candidate_cause = "insufficient_evidence"
            finding.confidence = "low"
            finding.justification = (
                "Counterevidence and re-check did not support congestion; "
                "abstaining due to insufficient evidence."
            )

        self.findings.append(finding)
        return finding
