"""Single AI agent baseline.

One agent sees all evidence and makes a diagnosis. Tests whether three
specialist agents + coordinator outperform a single generalist agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SingleAgentResult:
    case_id: str
    primary: str  # "benign" | "suspected_malicious" | "insufficient_evidence"
    secondary_cause: str | None
    confidence: str
    justification: str
    supporting_record_ids: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)


class SingleAgentBaseline:
    """Single generalist agent that reviews all evidence and decides."""

    def __init__(self) -> None:
        self.findings: list[SingleAgentResult] = []

    def diagnose(
        self,
        case_id: str,
        raw_sources: dict[str, Any],
        evidence_records: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> SingleAgentResult:
        watchdog = raw_sources.get("watchdog_direct_observation", {})
        received = watchdog.get("packets_overheard_received", 0)
        forwarded = watchdog.get("packets_overheard_forwarded", 0)
        avg_delay = watchdog.get("avg_forwarding_delay_ms", 0)
        route_changes = watchdog.get("observed_route_change_count", 0)
        rssi_samples = watchdog.get("watchdog_measured_rssi_from_node_dbm_samples", [])

        loss_ratio = 1 - (forwarded / received) if received > 0 else 0.0
        avg_rssi = (
            sum(s.get("value", 0) for s in rssi_samples) / len(rssi_samples)
            if rssi_samples else -100
        )

        # Simple rule-based single agent (no LLM needed for baseline)
        if received == 0:
            primary = "insufficient_evidence"
            secondary = None
            confidence = "low"
            justification = "No verified receipt at relay; cannot determine behavior."
        elif loss_ratio > 0.5 and avg_rssi > -85 and avg_delay < 100:
            # High loss with good link and low delay -> suspicious
            primary = "suspected_malicious"
            secondary = "malicious_blackhole" if loss_ratio > 0.8 else "malicious_selective_forwarding"
            confidence = "high"
            justification = (
                f"High loss ratio ({loss_ratio:.2f}) with good signal ({avg_rssi:.0f} dBm) "
                f"and low delay ({avg_delay:.0f} ms) suggests malicious dropping."
            )
        elif loss_ratio > 0.3 and (avg_rssi < -85 or route_changes >= 2):
            # Loss with bad link or mobility -> benign degradation
            primary = "benign"
            secondary = "honest_link_degradation" if avg_rssi < -85 else "honest_congestion_full_queue"
            confidence = "medium"
            justification = (
                f"Loss ratio ({loss_ratio:.2f}) explained by weak link ({avg_rssi:.0f} dBm) "
                f"or mobility ({route_changes} route changes)."
            )
        elif loss_ratio <= 0.1:
            primary = "benign"
            secondary = "honest_normal"
            confidence = "high"
            justification = f"Low loss ratio ({loss_ratio:.2f}); normal forwarding."
        else:
            primary = "insufficient_evidence"
            secondary = None
            confidence = "low"
            justification = (
                f"Ambiguous loss ratio ({loss_ratio:.2f}); evidence insufficient for a defensible decision."
            )

        result = SingleAgentResult(
            case_id=case_id,
            primary=primary,
            secondary_cause=secondary,
            confidence=confidence,
            justification=justification,
            supporting_record_ids=[],
            missing_info=[] if primary != "insufficient_evidence" else ["ambiguous_evidence"],
        )
        self.findings.append(result)
        return result
