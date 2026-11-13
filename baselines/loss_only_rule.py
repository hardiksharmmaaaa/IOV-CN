"""Loss-only threshold rule baseline.

Classifies a relay as suspected_malicious if its forwarding loss ratio exceeds
a tuned threshold. Simple but unfair to honest vehicles with bad links.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LossOnlyResult:
    case_id: str
    primary: str  # "suspected_malicious" | "benign" | "insufficient_evidence"
    loss_ratio: float
    threshold: float
    rule_applied: str


class LossOnlyRule:
    """Diagnoses based solely on packet loss percentage."""

    def __init__(self, threshold: float = 0.3):
        self.threshold = threshold

    def diagnose(
        self,
        case_id: str,
        raw_sources: dict[str, Any],
        **kwargs: Any,
    ) -> LossOnlyResult:
        watchdog = raw_sources.get("watchdog_direct_observation", {})
        received = watchdog.get("packets_overheard_received", 0)
        forwarded = watchdog.get("packets_overheard_forwarded", 0)

        loss_ratio = 1 - (forwarded / received) if received > 0 else 0.0

        if loss_ratio > self.threshold:
            primary = "suspected_malicious"
        else:
            primary = "benign"

        return LossOnlyResult(
            case_id=case_id,
            primary=primary,
            loss_ratio=loss_ratio,
            threshold=self.threshold,
            rule_applied=(
                f"loss_only: loss_ratio={loss_ratio:.3f} > threshold={self.threshold}"
                if primary == "suspected_malicious"
                else f"loss_only: loss_ratio={loss_ratio:.3f} <= threshold={self.threshold}"
            ),
        )
