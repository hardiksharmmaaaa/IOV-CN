"""Regression tests for the leakage-safe ML feature contract."""

from __future__ import annotations

import unittest
from pathlib import Path

from ml import FEATURE_NAMES, extract_features
from ml.dataset import LABELS, load_jsonl_cases


class MLFeatureContractTests(unittest.TestCase):
    def test_training_case_has_stable_feature_order(self) -> None:
        case = load_jsonl_cases(
            Path("Monitoring-Dataset") / "medium_train_sft.jsonl"
        )[0]
        vector = extract_features(case.raw_sources)
        self.assertEqual(vector.names, tuple(FEATURE_NAMES))
        self.assertEqual(len(vector.values), len(FEATURE_NAMES))
        self.assertTrue(all(isinstance(value, float) for value in vector.values))

    def test_missing_telemetry_is_marked(self) -> None:
        vector = extract_features({})
        self.assertEqual(vector.by_name["packets_received_missing"], 1.0)
        self.assertEqual(vector.by_name["queue_occupancy_missing"], 1.0)
        self.assertEqual(vector.by_name["watchdog_rssi_missing"], 1.0)

    def test_loader_keeps_labels_outside_raw_sources(self) -> None:
        case = load_jsonl_cases(
            Path("Monitoring-Dataset") / "medium_train_sft.jsonl"
        )[0]
        self.assertIn(case.label, LABELS)
        self.assertNotIn("ground_truth", case.raw_sources)
        self.assertNotIn("generation_case", case.raw_sources)


if __name__ == "__main__":
    unittest.main()
