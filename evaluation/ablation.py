"""Ablation and evidence-masking tests.

Tests the impact of removing key components:
1. No challenge round
2. No abstention (force decision)
3. Evidence masking (hide 10%, 30%, 50% of fields)

Compares results against the full proposed system.
"""

from __future__ import annotations

import copy
import random
from typing import Any

from controller import Coordinator


class AblationStudy:
    """Runs ablation experiments on the diagnosis pipeline."""

    def __init__(
        self,
        agents: dict[str, Any],
        evidence_tools: dict[str, Any],
        evidence_index: dict[str, list[dict[str, Any]]],
    ):
        self.agents = agents
        self.evidence_tools = evidence_tools
        self.evidence_index = evidence_index

    def run_full_system(
        self,
        case_id: str,
        monitored_node: str,
        window: dict[str, Any],
        raw_sources: dict[str, Any],
    ) -> dict[str, Any]:
        """Run the full proposed system with all components."""
        coordinator = Coordinator(
            agents=self._fresh_agents(),
            evidence_tools=self.evidence_tools,
            evidence_index=self.evidence_index,
        )
        result = coordinator.diagnose(
            case_id=case_id,
            monitored_node=monitored_node,
            window=window,
            raw_sources=raw_sources,
        )
        return {
            "decision": result.decision.primary,
            "challenge_rounds": result.challenge_rounds,
            "confidence": result.decision.confidence,
            "agent_findings": result.agent_findings,
            "rule_applied": result.decision.rule_applied,
        }

    def run_no_challenge_round(
        self,
        case_id: str,
        monitored_node: str,
        window: dict[str, Any],
        raw_sources: dict[str, Any],
    ) -> dict[str, Any]:
        """Run system WITHOUT the bounded challenge round.

        Agents investigate once, coordinator decides immediately.
        """
        agent_findings: dict[str, Any] = {}
        for agent_name, agent in self._fresh_agents().items():
            finding = agent.investigate(
                case_id=case_id,
                raw_sources=raw_sources,
                available_tools=self.evidence_tools,
            )
            agent_findings[agent_name] = {
                "candidate_cause": finding.candidate_cause,
                "confidence": finding.confidence,
                "supporting_record_ids": finding.supporting_record_ids,
                "counterevidence_ids": finding.counterevidence_ids,
                "missing_fields": finding.missing_fields,
                "justification": finding.justification,
                "tool_calls_used": finding.tool_calls_used,
            }

        # Apply decision rules directly without challenge
        decision = self._apply_decision_rules(agent_findings, raw_sources)
        return {
            "decision": decision.primary,
            "challenge_rounds": 0,
            "confidence": decision.confidence,
            "agent_findings": agent_findings,
            "rule_applied": decision.rule_applied,
        }

    def run_no_abstention(
        self,
        case_id: str,
        monitored_node: str,
        window: dict[str, Any],
        raw_sources: dict[str, Any],
    ) -> dict[str, Any]:
        """Run system WITHOUT abstention — forces a benign/malicious decision.

        When agents would abstain, falls back to majority vote of concrete causes.
        """
        coordinator = Coordinator(
            agents=self._fresh_agents(),
            evidence_tools=self.evidence_tools,
            evidence_index=self.evidence_index,
        )
        result = coordinator.diagnose(
            case_id=case_id,
            monitored_node=monitored_node,
            window=window,
            raw_sources=raw_sources,
        )

        # If abstained, force a decision via majority vote
        if result.decision.primary == "insufficient_evidence":
            causes = {
                name: f.get("candidate_cause", "")
                for name, f in result.agent_findings.items()
            }
            malicious = sum(
                1 for c in causes.values() if c in ("malicious_blackhole", "malicious_selective_forwarding")
            )
            benign = sum(
                1 for c in causes.values() if c in ("honest_congestion_full_queue", "honest_link_degradation")
            )
            forced = "suspected_malicious" if malicious > benign else "benign"
            return {
                "decision": forced,
                "challenge_rounds": result.challenge_rounds,
                "confidence": "low",
                "agent_findings": result.agent_findings,
                "rule_applied": "forced_decision: no_abstention_majority_vote",
            }

        return {
            "decision": result.decision.primary,
            "challenge_rounds": result.challenge_rounds,
            "confidence": result.decision.confidence,
            "agent_findings": result.agent_findings,
            "rule_applied": result.decision.rule_applied,
        }

    def run_with_masked_evidence(
        self,
        case_id: str,
        monitored_node: str,
        window: dict[str, Any],
        raw_sources: dict[str, Any],
        mask_ratio: float = 0.1,
        seed: int = 42,
    ) -> dict[str, Any]:
        """Run system with a fraction of evidence fields hidden.

        mask_ratio: 0.1, 0.3, or 0.5 — fraction of records to hide per source.
        """
        masked_raw = self._mask_evidence(raw_sources, mask_ratio, seed)

        coordinator = Coordinator(
            agents=self._fresh_agents(),
            evidence_tools=self.evidence_tools,
            evidence_index=self.evidence_index,
        )
        result = coordinator.diagnose(
            case_id=case_id,
            monitored_node=monitored_node,
            window=window,
            raw_sources=masked_raw,
        )
        return {
            "decision": result.decision.primary,
            "challenge_rounds": result.challenge_rounds,
            "confidence": result.decision.confidence,
            "agent_findings": result.agent_findings,
            "rule_applied": result.decision.rule_applied,
            "mask_ratio": mask_ratio,
        }

    def _fresh_agents(self) -> dict[str, Any]:
        """Return fresh agent instances (no state leakage between runs)."""
        from agents import CongestionAgent, WirelessMobilityAgent, ForwardingPatternAgent
        return {
            "congestion_agent": CongestionAgent(),
            "wireless_mobility_agent": WirelessMobilityAgent(),
            "forwarding_pattern_agent": ForwardingPatternAgent(),
        }

    def _apply_decision_rules(
        self,
        agent_findings: dict[str, Any],
        raw_sources: dict[str, Any],
    ) -> Any:
        """Inline decision rules (same logic as coordinator but without challenge)."""
        from controller.diagnosis import Decision

        causes = {
            name: f.get("candidate_cause", "insufficient_evidence")
            for name, f in agent_findings.items()
        }

        congestion_cause = causes.get("congestion_agent", "")
        wireless_cause = causes.get("wireless_mobility_agent", "")
        pattern_cause = causes.get("forwarding_pattern_agent", "")

        watchdog = raw_sources.get("watchdog_direct_observation", {})
        packets_received = watchdog.get("packets_overheard_received", 0)
        packets_forwarded = watchdog.get("packets_overheard_forwarded", 0)

        congestion_supports_benign = congestion_cause == "honest_congestion_full_queue"
        wireless_supports_benign = wireless_cause == "honest_link_degradation"
        pattern_suggests_malicious = pattern_cause in ("malicious_blackhole", "malicious_selective_forwarding")

        benign_votes = sum(
            1 for c in causes.values() if c in ("honest_congestion_full_queue", "honest_link_degradation")
        )
        malicious_votes = sum(
            1 for c in causes.values() if c in ("malicious_blackhole", "malicious_selective_forwarding")
        )

        if packets_received > 0 and packets_forwarded < packets_received:
            if pattern_suggests_malicious and not congestion_supports_benign and not wireless_supports_benign:
                if malicious_votes >= 1 and benign_votes == 0:
                    return Decision(
                        primary="suspected_malicious",
                        secondary_cause=pattern_cause,
                        supporting_record_ids=[],
                        contradictory_evidence=[],
                        missing_info=[],
                        rule_applied="no_challenge: suspected_malicious",
                        confidence="high",
                    )

        if congestion_supports_benign or wireless_supports_benign:
            if malicious_votes == 0:
                return Decision(
                    primary="benign",
                    secondary_cause=congestion_cause or wireless_cause,
                    supporting_record_ids=[],
                    contradictory_evidence=[],
                    missing_info=[],
                    rule_applied="no_challenge: benign",
                    confidence="medium",
                )

        return Decision(
            primary="insufficient_evidence",
            secondary_cause=None,
            supporting_record_ids=[],
            contradictory_evidence=[],
            missing_info=["no_challenge_abstention"],
            rule_applied="no_challenge: insufficient_evidence",
            confidence="low",
        )

    def _mask_evidence(
        self,
        raw_sources: dict[str, Any],
        mask_ratio: float,
        seed: int,
    ) -> dict[str, Any]:
        """Randomly hide a fraction of evidence records per source."""
        rng = random.Random(seed)
        masked = copy.deepcopy(raw_sources)

        # Mask RSSI samples in watchdog
        wdo = masked.get("watchdog_direct_observation", {})
        rssi = wdo.get("watchdog_measured_rssi_from_node_dbm_samples", [])
        if rssi:
            keep = max(1, int(len(rssi) * (1 - mask_ratio)))
            wdo["watchdog_measured_rssi_from_node_dbm_samples"] = rng.sample(rssi, keep)

        # Mask queue samples
        nnq = masked.get("node_or_neighbor_query", {})
        node_report = nnq.get("monitored_node_report", {})
        queue_samples = node_report.get("queue_occupancy_percent_samples", [])
        if queue_samples:
            keep = max(1, int(len(queue_samples) * (1 - mask_ratio)))
            node_report["queue_occupancy_percent_samples"] = rng.sample(queue_samples, keep)

        # Mask link quality samples
        rlq = nnq.get("reported_link_quality_window", {})
        for key in ("upstream_to_monitored_rssi_dbm_samples", "monitored_to_downstream_rssi_dbm_samples"):
            samples = rlq.get(key, [])
            if samples:
                keep = max(1, int(len(samples) * (1 - mask_ratio)))
                rlq[key] = rng.sample(samples, keep)

        # Mask mobility samples
        pm = masked.get("protocol_message", {})
        mobility = pm.get("advertised_mobility_window", {})
        for key in ("speed_samples_mps", "heading_samples_deg"):
            samples = mobility.get(key, [])
            if samples:
                keep = max(1, int(len(samples) * (1 - mask_ratio)))
                mobility[key] = rng.sample(samples, keep)

        willingness = pm.get("willingness_samples", [])
        if willingness:
            keep = max(1, int(len(willingness) * (1 - mask_ratio)))
            pm["willingness_samples"] = rng.sample(willingness, keep)

        return masked


def run_ablation_suite(
    cases: list[dict[str, Any]],
    agents: dict[str, Any],
    evidence_tools: dict[str, Any],
    evidence_index: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Run all ablation variants on a list of cases.

    Returns results per variant for comparison.
    """
    study = AblationStudy(agents, evidence_tools, evidence_index)
    variants = {
        "full_system": [],
        "no_challenge_round": [],
        "no_abstention": [],
        "masked_10pct": [],
        "masked_30pct": [],
        "masked_50pct": [],
    }

    for case in cases:
        base = {
            "case_id": case["case_id"],
            "true_behavior": case.get("true_behavior"),
            "monitored_node": case["monitored_node"],
        }

        full = study.run_full_system(
            case["case_id"], case["monitored_node"], case["window"], case["raw_sources"]
        )
        variants["full_system"].append({**base, **full})

        no_challenge = study.run_no_challenge_round(
            case["case_id"], case["monitored_node"], case["window"], case["raw_sources"]
        )
        variants["no_challenge_round"].append({**base, **no_challenge})

        no_abstention = study.run_no_abstention(
            case["case_id"], case["monitored_node"], case["window"], case["raw_sources"]
        )
        variants["no_abstention"].append({**base, **no_abstention})

        for ratio, key in [(0.1, "masked_10pct"), (0.3, "masked_30pct"), (0.5, "masked_50pct")]:
            masked = study.run_with_masked_evidence(
                case["case_id"], case["monitored_node"], case["window"], case["raw_sources"],
                mask_ratio=ratio,
            )
            variants[key].append({**base, **masked})

    return variants
