"""Leakage-safe feature extraction for recorded IoV monitoring cases.

The extractor consumes only ``raw_sources`` from a case.  Ground-truth labels,
metadata such as ``generation_case``, and split information are deliberately
not accepted as inputs.  Every aggregate has a corresponding missingness
feature so an absent telemetry field is not confused with a measured zero.

The feature order is part of the model contract.  Training and inference must
use :data:`FEATURE_NAMES` in exactly the same order.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any, Iterable, Mapping


def _finite_number(value: Any) -> float | None:
    """Return a numeric value or ``None`` for missing/non-numeric input."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if numeric == numeric and abs(numeric) != float("inf") else None
    return None


def _numbers(values: Iterable[Any]) -> list[float]:
    return [number for value in values if (number := _finite_number(value)) is not None]


def _stats(values: Iterable[Any]) -> tuple[float, float, float, float, float, float]:
    """Return mean, min, max, std, count, and missing flag for a numeric series."""
    numbers = _numbers(values)
    if not numbers:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 1.0

    mean = sum(numbers) / len(numbers)
    variance = sum((value - mean) ** 2 for value in numbers) / len(numbers)
    return (
        mean,
        min(numbers),
        max(numbers),
        sqrt(variance),
        float(len(numbers)),
        0.0,
    )


def _sample_values(samples: Any) -> list[float]:
    if not isinstance(samples, list):
        return []
    return _numbers(
        sample.get("value")
        for sample in samples
        if isinstance(sample, Mapping)
    )


def _mean(values: Iterable[Any]) -> tuple[float, float]:
    numbers = _numbers(values)
    return (sum(numbers) / len(numbers), 0.0) if numbers else (0.0, 1.0)


def _record_stats(
    features: dict[str, float],
    prefix: str,
    values: Iterable[Any],
) -> None:
    mean, minimum, maximum, std, count, missing = _stats(values)
    features.update(
        {
            f"{prefix}_mean": mean,
            f"{prefix}_min": minimum,
            f"{prefix}_max": maximum,
            f"{prefix}_std": std,
            f"{prefix}_count": count,
            f"{prefix}_missing": missing,
        }
    )


def _heading_change_stats(samples: Any) -> tuple[float, float, float]:
    """Return mean, maximum, and missing flag for circular heading changes."""
    if not isinstance(samples, list):
        return 0.0, 0.0, 1.0
    headings = _numbers(
        sample.get("value")
        for sample in samples
        if isinstance(sample, Mapping)
    )
    if len(headings) < 2:
        return 0.0, 0.0, 1.0
    changes = []
    for previous, current in zip(headings, headings[1:]):
        difference = abs(current - previous) % 360.0
        changes.append(min(difference, 360.0 - difference))
    return sum(changes) / len(changes), max(changes), 0.0


def _watchdog_report_values(raw_sources: Mapping[str, Any]) -> dict[str, list[Any]]:
    other = raw_sources.get("other_watchdog_query", {})
    reports = other.get("watchdog_reports", []) if isinstance(other, Mapping) else []
    if not isinstance(reports, list):
        reports = []
    return {
        "received": [r.get("packets_overheard_received") for r in reports if isinstance(r, Mapping)],
        "forwarded": [r.get("packets_overheard_forwarded") for r in reports if isinstance(r, Mapping)],
        "rssi": [r.get("avg_rssi_from_monitored_node_dbm") for r in reports if isinstance(r, Mapping)],
        "age": [r.get("report_age_s") for r in reports if isinstance(r, Mapping)],
    }


BASE_FEATURE_NAMES = [
    "packets_received",
    "packets_forwarded",
    "loss_ratio",
    "avg_forwarding_delay_ms",
    "observed_route_change_count",
    "packets_received_missing",
    "packets_forwarded_missing",
    "avg_forwarding_delay_ms_missing",
    "observed_route_change_count_missing",
]

STAT_FEATURE_NAMES = [
    f"{prefix}_{stat}"
    for prefix in (
        "watchdog_rssi",
        "upstream_rssi",
        "downstream_rssi",
        "queue_occupancy",
        "speed_mps",
        "heading_change_deg",
        "other_watchdog_received",
        "other_watchdog_forwarded",
        "other_watchdog_rssi",
        "other_watchdog_age_s",
    )
    for stat in ("mean", "min", "max", "std", "count", "missing")
]

EXTRA_FEATURE_NAMES = [
    "queue_drop_percent",
    "queue_drop_percent_missing",
    "heading_change_mean_deg",
    "heading_change_max_deg",
    "heading_change_missing",
    "other_watchdog_count",
    "other_watchdog_count_missing",
]

FEATURE_NAMES = BASE_FEATURE_NAMES + STAT_FEATURE_NAMES + EXTRA_FEATURE_NAMES


@dataclass(frozen=True)
class FeatureVector:
    """A model-ready vector plus named values for diagnostics."""

    names: tuple[str, ...]
    values: tuple[float, ...]
    by_name: dict[str, float]


def extract_features(raw_sources: Mapping[str, Any]) -> FeatureVector:
    """Extract the fixed, leakage-safe feature vector from one case.

    Missing numeric telemetry receives a neutral numeric placeholder together
    with a ``*_missing`` indicator.  This is a representation choice for the
    model, not an assertion that the missing measurement was zero.
    """
    watchdog = raw_sources.get("watchdog_direct_observation", {})
    if not isinstance(watchdog, Mapping):
        watchdog = {}

    queue_report = raw_sources.get("node_or_neighbor_query", {})
    if not isinstance(queue_report, Mapping):
        queue_report = {}
    monitored_report = queue_report.get("monitored_node_report", {})
    if not isinstance(monitored_report, Mapping):
        monitored_report = {}
    link_report = queue_report.get("reported_link_quality_window", {})
    if not isinstance(link_report, Mapping):
        link_report = {}

    received = _finite_number(watchdog.get("packets_overheard_received"))
    forwarded = _finite_number(watchdog.get("packets_overheard_forwarded"))
    loss_ratio = (
        1.0 - forwarded / received
        if received is not None and received > 0 and forwarded is not None
        else 0.0
    )

    features: dict[str, float] = {
        "packets_received": received if received is not None else 0.0,
        "packets_forwarded": forwarded if forwarded is not None else 0.0,
        "loss_ratio": loss_ratio,
        "avg_forwarding_delay_ms": _finite_number(watchdog.get("avg_forwarding_delay_ms")) or 0.0,
        "observed_route_change_count": _finite_number(watchdog.get("observed_route_change_count")) or 0.0,
        "packets_received_missing": 0.0 if received is not None else 1.0,
        "packets_forwarded_missing": 0.0 if forwarded is not None else 1.0,
        "avg_forwarding_delay_ms_missing": 0.0 if _finite_number(watchdog.get("avg_forwarding_delay_ms")) is not None else 1.0,
        "observed_route_change_count_missing": 0.0 if _finite_number(watchdog.get("observed_route_change_count")) is not None else 1.0,
    }

    _record_stats(
        features,
        "watchdog_rssi",
        _sample_values(watchdog.get("watchdog_measured_rssi_from_node_dbm_samples", [])),
    )
    _record_stats(
        features,
        "upstream_rssi",
        _sample_values(link_report.get("upstream_to_monitored_rssi_dbm_samples", [])),
    )
    _record_stats(
        features,
        "downstream_rssi",
        _sample_values(link_report.get("monitored_to_downstream_rssi_dbm_samples", [])),
    )
    _record_stats(
        features,
        "queue_occupancy",
        _sample_values(monitored_report.get("queue_occupancy_percent_samples", [])),
    )

    mobility = raw_sources.get("protocol_message", {})
    if not isinstance(mobility, Mapping):
        mobility = {}
    advertised = mobility.get("advertised_mobility_window", {})
    if not isinstance(advertised, Mapping):
        advertised = {}
    _record_stats(features, "speed_mps", _sample_values(advertised.get("speed_samples_mps", [])))

    heading_mean, heading_max, heading_missing = _heading_change_stats(
        advertised.get("heading_samples_deg", [])
    )
    features["heading_change_mean_deg"] = heading_mean
    features["heading_change_max_deg"] = heading_max
    features["heading_change_missing"] = heading_missing
    # Keep the standard-stat slot populated for a stable schema.  Heading
    # changes are already represented by the dedicated circular statistics.
    features.update(
        {
            "heading_change_deg_mean": heading_mean,
            "heading_change_deg_min": 0.0,
            "heading_change_deg_max": heading_max,
            "heading_change_deg_std": 0.0,
            "heading_change_deg_count": 0.0 if heading_missing else 1.0,
            "heading_change_deg_missing": heading_missing,
        }
    )

    report_values = _watchdog_report_values(raw_sources)
    _record_stats(features, "other_watchdog_received", report_values["received"])
    _record_stats(features, "other_watchdog_forwarded", report_values["forwarded"])
    _record_stats(features, "other_watchdog_rssi", report_values["rssi"])
    _record_stats(features, "other_watchdog_age_s", report_values["age"])

    queue_drop = _finite_number(monitored_report.get("queue_drop_percent"))
    features["queue_drop_percent"] = queue_drop if queue_drop is not None else 0.0
    features["queue_drop_percent_missing"] = 0.0 if queue_drop is not None else 1.0
    features["other_watchdog_count"] = float(len(report_values["received"]))
    features["other_watchdog_count_missing"] = 0.0 if report_values["received"] else 1.0

    missing_names = [name for name in FEATURE_NAMES if name not in features]
    if missing_names:
        raise ValueError(f"Feature contract is incomplete: {missing_names}")

    ordered = {name: float(features[name]) for name in FEATURE_NAMES}
    return FeatureVector(
        names=tuple(FEATURE_NAMES),
        values=tuple(ordered.values()),
        by_name=ordered,
    )
