"""Dataset loading utilities for supervised IoV model training."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


LABELS = (
    "honest_normal",
    "honest_congestion_full_queue",
    "honest_link_degradation",
    "malicious_blackhole",
    "malicious_selective_forwarding",
    "uncertain_needs_more_evidence",
)


@dataclass(frozen=True)
class LabeledCase:
    """One training/evaluation example with labels kept outside raw telemetry."""

    case_id: str
    raw_sources: dict[str, Any]
    label: str


def iter_jsonl_cases(path: str | Path) -> Iterator[LabeledCase]:
    """Yield labeled cases from an SFT-style JSONL file.

    Only the user payload is passed to feature extraction.  The top-level
    ``ground_truth.true_behavior`` is used solely as the supervised target.
    """
    dataset_path = Path(path)
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                user_message = next(
                    message
                    for message in row.get("messages", [])
                    if message.get("role") == "user"
                )
                payload = json.loads(user_message["content"])
                label = row.get("ground_truth", {}).get("true_behavior")
                case_id = row["sample_id"]
                raw_sources = payload["raw_sources"]
            except (KeyError, StopIteration, TypeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"Invalid case at {dataset_path}:{line_number}: {exc}"
                ) from exc

            if label not in LABELS:
                raise ValueError(
                    f"Unsupported label at {dataset_path}:{line_number}: {label!r}"
                )
            if not isinstance(raw_sources, dict):
                raise ValueError(
                    f"raw_sources is not an object at {dataset_path}:{line_number}"
                )
            yield LabeledCase(case_id=case_id, raw_sources=raw_sources, label=label)


def load_jsonl_cases(path: str | Path) -> list[LabeledCase]:
    """Load all labeled cases from one split."""
    return list(iter_jsonl_cases(path))
