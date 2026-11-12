"""Wireless and mobility specialist agent.

Examines link measurements, retransmissions, connection changes, and monitor
visibility to determine whether connectivity or incomplete observation explains
missing forwarding events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WirelessMobilityFinding:
    candidate_cause: str
    supporting_record_ids: list[str] = field(default_factory=list)
    counterevidence_ids: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    justification: str = ""
    confidence: str = "low"
    tool_calls_used: int = 0


class WirelessMobilityAgent:
    """Specialist agent for wireless and mobility evidence."""

    name = "wireless_mobility_agent"
    role = "Determine whether connectivity or incomplete observation explains missing forwarding events."

    evidence_tools = [
        "get_link_evidence",
        "get_forwarding_pattern",
    ]

    max_tool_calls = 2

    def __init__(self) -> None:
        self.findings: list[WirelessMobilityFinding] = []

    def investigate(
        self,
        case_id: str,
        raw_sources: dict[str, Any],
        available_tools: dict[str, Any],
    ) -> WirelessMobilityFinding:
        """Run wireless/mobility investigation on a relay case."""
        finding = WirelessMobilityFinding(
            candidate_cause="unknown",
            confidence="low",
        )

        link_records = self._call_tool(
            available_tools,
            "get_link_evidence",
            case_id=case_id,
        )
        finding.tool_calls_used += 1

        pattern_records = self._call_tool(
            available_tools,
            "get_forwarding_pattern",
            case_id=case_id,
        )
        finding.tool_calls_used += 1

        finding.supporting_record_ids = [
            r.get("record_id") for r in link_records if r.get("case_id") == case_id
        ]
        finding.supporting_record_ids += [
            r.get("record_id") for r in pattern_records if r.get("case_id") == case_id
        ]

        weak_link = any(
            r.get("rssi_dbm", 0) < -85 for r in link_records
        )
        route_changes = any(
            r.get("observed_route_change_count", 0) >= 2 for r in link_records
        )
        low_visibility = any(
            r.get("monitor_visibility_pct", 100) < 70 for r in link_records
        )

        if weak_link or route_changes or low_visibility:
            finding.candidate_cause = "honest_link_degradation"
            finding.confidence = "medium"
            finding.justification = (
                "Weak RSSI, frequent route changes, or low monitor visibility "
                "explain missing forwarding events as benign link degradation."
            )
        else:
            finding.candidate_cause = "insufficient_evidence"
            finding.confidence = "low"
            finding.justification = (
                "No link, mobility, or visibility evidence supports degradation."
            )
            if not link_records:
                finding.missing_fields.append("link_evidence")

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
    ) -> WirelessMobilityFinding:
        """Single revision round after challenge. Allows one additional tool call."""
        finding = WirelessMobilityFinding(
            candidate_cause="unknown",
            confidence="low",
        )

        finding.counterevidence_ids = [
            r.get("record_id") for r in counterevidence if r.get("case_id") == case_id
        ]

        extra = self._call_tool(
            available_tools,
            "get_link_evidence",
            case_id=case_id,
            include_counterevidence=True,
        )
        finding.tool_calls_used = 1

        weak_link = any(
            r.get("rssi_dbm", 0) < -85 for r in extra
        )
        low_visibility = any(
            r.get("monitor_visibility_pct", 100) < 70 for r in extra
        )

        if weak_link or low_visibility:
            finding.candidate_cause = "honest_link_degradation"
            finding.confidence = "medium"
            finding.justification = (
                "Counterevidence reviewed; weak link or low visibility still "
                "supports benign link degradation."
            )
        else:
            finding.candidate_cause = "insufficient_evidence"
            finding.confidence = "low"
            finding.justification = (
                "Re-check after counterevidence did not support link degradation; "
                "abstaining."
            )

        self.findings.append(finding)
        return finding
