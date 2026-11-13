"""Evidence adapter for the IoV Forwarding Diagnosis dataset.

Reads JSONL monitoring files, normalizes timestamps, assigns immutable record
IDs, groups observations by relay and window, and exposes a queryable evidence
index that the specialist agents consume through read-only tools.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class EvidenceRecord:
    """A single immutable evidence record."""

    record_id: str
    case_id: str
    monitored_node: str
    window_start_s: int
    window_end_s: int
    source: str  # "queue" | "link" | "forwarding" | "mobility"
    timestamp_s: int
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Case:
    """A normalized monitoring case for one relay over one window."""

    case_id: str
    session_id: str
    monitored_node: str
    window: dict[str, Any]
    raw_sources: dict[str, Any]
    ground_truth: dict[str, Any] | None = None
    generation_case: str | None = None
    difficulty: str | None = None


class EvidenceAdapter:
    """Ingests JSONL monitoring files and builds a queryable evidence index."""

    def __init__(self, dataset_dir: str | None = None):
        self.dataset_dir = dataset_dir
        self.cases: dict[str, Case] = {}
        self.records: list[EvidenceRecord] = []
        self._record_counter = 0
        self._loaded_files: list[str] = []

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #
    def load_split(self, split_file: str) -> int:
        """Load one JSONL split file. Returns number of cases loaded."""
        path = split_file
        if self.dataset_dir and not os.path.isabs(split_file):
            path = os.path.join(self.dataset_dir, split_file)

        if not os.path.exists(path):
            raise FileNotFoundError(f"Split file not found: {path}")

        count = 0
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                case = self._parse_line(line)
                self.cases[case.case_id] = case
                self._build_records_for_case(case)
                count += 1
        self._loaded_files.append(path)
        return count

    def load_all_splits(self) -> dict[str, int]:
        """Load all JSONL files in the dataset directory. Returns {file: count}."""
        if not self.dataset_dir:
            raise ValueError("dataset_dir not set; cannot auto-discover splits")
        counts: dict[str, int] = {}
        for fname in sorted(os.listdir(self.dataset_dir)):
            if fname.endswith(".jsonl"):
                counts[fname] = self.load_split(fname)
        return counts

    # ------------------------------------------------------------------ #
    # Parsing
    # ------------------------------------------------------------------ #
    def _parse_line(self, line: str) -> Case:
        data = json.loads(line)

        # The user message content is a JSON string containing the case payload
        user_content = None
        for msg in data.get("messages", []):
            if msg.get("role") == "user":
                user_content = json.loads(msg["content"])
                break
        if user_content is None:
            raise ValueError("No user message with case payload found")

        case_id = data["sample_id"]
        monitored_node = user_content["monitored_node"]
        window = user_content["window"]
        raw_sources = user_content["raw_sources"]
        session_id = user_content.get("session_id", case_id)

        ground_truth = data.get("ground_truth")
        metadata = data.get("metadata", {})

        return Case(
            case_id=case_id,
            session_id=session_id,
            monitored_node=monitored_node,
            window=window,
            raw_sources=raw_sources,
            ground_truth=ground_truth,
            generation_case=metadata.get("generation_case"),
            difficulty=metadata.get("difficulty"),
        )

    def _build_records_for_case(self, case: Case) -> None:
        """Flatten raw_sources into immutable EvidenceRecords."""
        ws = case.window.get("start_s", 0)
        we = case.window.get("end_s", 0)
        node = case.monitored_node
        cid = case.case_id
        rs = case.raw_sources

        # ---- Forwarding records (watchdog_direct_observation) ----
        wdo = rs.get("watchdog_direct_observation", {})
        self._add_record(
            cid, node, ws, we, "forwarding", ws,
            {
                "packets_overheard_received": wdo.get("packets_overheard_received"),
                "packets_overheard_forwarded": wdo.get("packets_overheard_forwarded"),
                "avg_forwarding_delay_ms": wdo.get("avg_forwarding_delay_ms"),
                "observed_route_change_count": wdo.get("observed_route_change_count"),
            },
        )

        # RSSI samples from watchdog
        for sample in wdo.get("watchdog_measured_rssi_from_node_dbm_samples", []):
            self._add_record(
                cid, node, ws, we, "link", int(sample.get("t_s", ws)),
                {"rssi_dbm": sample.get("value"), "source": "watchdog_rx"},
            )

        # ---- Queue records (node_or_neighbor_query) ----
        nnq = rs.get("node_or_neighbor_query", {})
        node_report = nnq.get("monitored_node_report", {})
        for sample in node_report.get("queue_occupancy_percent_samples", []):
            self._add_record(
                cid, node, ws, we, "queue", int(sample.get("t_s", ws)),
                {"queue_occupancy_pct": sample.get("value")},
            )
        if node_report.get("queue_drop_percent") is not None:
            self._add_record(
                cid, node, ws, we, "queue", ws,
                {"queue_drop_percent": node_report.get("queue_drop_percent")},
            )

        # ---- Link records (reported_link_quality_window) ----
        rlq = nnq.get("reported_link_quality_window", {})
        for sample in rlq.get("upstream_to_monitored_rssi_dbm_samples", []):
            self._add_record(
                cid, node, ws, we, "link", int(sample.get("t_s", ws)),
                {"rssi_dbm": sample.get("value"), "source": "upstream_to_monitored"},
            )
        for sample in rlq.get("monitored_to_downstream_rssi_dbm_samples", []):
            self._add_record(
                cid, node, ws, we, "link", int(sample.get("t_s", ws)),
                {"rssi_dbm": sample.get("value"), "source": "monitored_to_downstream"},
            )

        # ---- Mobility records (protocol_message advertised_mobility_window) ----
        pm = rs.get("protocol_message", {})
        mobility = pm.get("advertised_mobility_window", {})
        for sample in mobility.get("speed_samples_mps", []):
            self._add_record(
                cid, node, ws, we, "mobility", int(sample.get("t_s", ws)),
                {"speed_mps": sample.get("value")},
            )
        for sample in mobility.get("heading_samples_deg", []):
            self._add_record(
                cid, node, ws, we, "mobility", int(sample.get("t_s", ws)),
                {"heading_deg": sample.get("value")},
            )

        # Willingness samples
        for sample in pm.get("willingness_samples", []):
            self._add_record(
                cid, node, ws, we, "mobility", int(sample.get("t_s", ws)),
                {"willingness": sample.get("value")},
            )

    def _add_record(
        self,
        case_id: str,
        monitored_node: str,
        window_start_s: int,
        window_end_s: int,
        source: str,
        timestamp_s: int,
        payload: dict[str, Any],
    ) -> None:
        self._record_counter += 1
        record = EvidenceRecord(
            record_id=f"REC_{self._record_counter:06d}",
            case_id=case_id,
            monitored_node=monitored_node,
            window_start_s=window_start_s,
            window_end_s=window_end_s,
            source=source,
            timestamp_s=timestamp_s,
            payload=payload,
        )
        self.records.append(record)

    # ------------------------------------------------------------------ #
    # Query API (read-only tools for agents)
    # ------------------------------------------------------------------ #
    def get_case(self, case_id: str) -> Case | None:
        return self.cases.get(case_id)

    def list_case_ids(self) -> list[str]:
        return sorted(self.cases.keys())

    def get_queue_evidence(self, case_id: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Read-only: queue occupancy and drop records for a case."""
        return self._records_for(case_id, "queue")

    def get_link_evidence(self, case_id: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Read-only: link/RSSI records for a case."""
        return self._records_for(case_id, "link")

    def get_forwarding_pattern(
        self, case_id: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Read-only: forwarding pattern records for a case."""
        return self._records_for(case_id, "forwarding")

    def get_mobility_evidence(self, case_id: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Read-only: mobility records for a case."""
        return self._records_for(case_id, "mobility")

    def _records_for(self, case_id: str, source: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for r in self.records:
            if r.case_id == case_id and r.source == source:
                out.append(
                    {
                        "record_id": r.record_id,
                        "case_id": r.case_id,
                        "monitored_node": r.monitored_node,
                        "timestamp_s": r.timestamp_s,
                        "source": r.source,
                        **r.payload,
                    }
                )
        return out

    def get_evidence_index(self) -> dict[str, list[dict[str, Any]]]:
        """Return full index grouped by case_id for the validator."""
        index: dict[str, list[dict[str, Any]]] = {}
        for r in self.records:
            index.setdefault(r.case_id, []).append(
                {
                    "record_id": r.record_id,
                    "case_id": r.case_id,
                    "monitored_node": r.monitored_node,
                    "timestamp_s": r.timestamp_s,
                    "source": r.source,
                    **r.payload,
                }
            )
        return index

    def stats(self) -> dict[str, Any]:
        source_counts: dict[str, int] = {}
        for r in self.records:
            source_counts[r.source] = source_counts.get(r.source, 0) + 1
        return {
            "cases_loaded": len(self.cases),
            "records_total": len(self.records),
            "records_by_source": source_counts,
            "files_loaded": self._loaded_files,
        }
