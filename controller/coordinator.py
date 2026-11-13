"""Coordinator — the final judge.

Orchestrates the three specialist agents, validates findings, runs a bounded
challenge round when agents disagree, and applies decision rules to produce:

- benign
- suspected_malicious
- insufficient_evidence
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .diagnosis import DiagnosisResult, Decision
from .validator import EvidenceValidator


@dataclass
class AgentConfig:
    name: str
    agent: Any
    evidence_tools: list[str]


class Coordinator:
    """Deterministic coordinator that judges relay forwarding behavior."""

    def __init__(
        self,
        agents: dict[str, Any],
        evidence_tools: dict[str, Any],
        evidence_index: dict[str, list[dict[str, Any]]] | None = None,
    ):
        self.agents = agents
        self.evidence_tools = evidence_tools
        self.validator = EvidenceValidator(evidence_index)

    def diagnose(
        self,
        case_id: str,
        monitored_node: str,
        window: dict[str, Any],
        raw_sources: dict[str, Any],
    ) -> DiagnosisResult:
        """Run the full diagnosis pipeline for one case."""
        result = DiagnosisResult(
            case_id=case_id,
            monitored_node=monitored_node,
            window=window,
        )

        # Stage 1: Run all specialist agents in parallel (sequential here for simplicity)
        agent_findings: dict[str, Any] = {}
        for agent_name, agent in self.agents.items():
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
            result.trace.append(
                {
                    "stage": "agent_investigation",
                    "agent": agent_name,
                    "finding": agent_findings[agent_name],
                }
            )

        result.agent_findings = agent_findings

        # Stage 2: Validate all findings
        validation_passed = True
        for agent_name, finding_dict in agent_findings.items():
            is_valid, issues = self.validator.validate_finding(case_id, finding_dict)
            if not is_valid:
                validation_passed = False
                # Attempt one formatting repair
                repaired = self.validator.attempt_repair(case_id, finding_dict)
                is_valid_after, issues_after = self.validator.validate_finding(
                    case_id, repaired
                )
                agent_findings[agent_name] = repaired
                result.trace.append(
                    {
                        "stage": "validation_repair",
                        "agent": agent_name,
                        "issues": issues,
                        "repaired": is_valid_after,
                        "remaining_issues": issues_after,
                    }
                )
            else:
                result.trace.append(
                    {
                        "stage": "validation",
                        "agent": agent_name,
                        "status": "passed",
                    }
                )

        # Stage 3: Check for agent disagreement
        candidate_causes = {
            name: f["candidate_cause"]
            for name, f in agent_findings.items()
        }
        unique_causes = set(candidate_causes.values())

        # Concrete (non-abstained) causes
        concrete_causes = {
            name: c for name, c in candidate_causes.items()
            if c != "insufficient_evidence"
        }
        unique_concrete = set(concrete_causes.values())

        challenge_rounds = 0
        # Agents disagree on concrete causes -> bounded challenge round
        if len(unique_concrete) > 1:
            challenge_rounds = 1
            result.trace.append(
                {
                    "stage": "challenge_round",
                    "round": challenge_rounds,
                    "conflicting_agents": list(candidate_causes.keys()),
                    "candidate_causes": candidate_causes,
                }
            )

            for agent_name in candidate_causes:
                agent = self.agents[agent_name]
                counterevidence = self._gather_counterevidence(
                    case_id, agent_name, agent_findings
                )
                revised = agent.revise(
                    case_id=case_id,
                    counterevidence=counterevidence,
                    raw_sources=raw_sources,
                    available_tools=self.evidence_tools,
                )
                agent_findings[agent_name] = {
                    "candidate_cause": revised.candidate_cause,
                    "confidence": revised.confidence,
                    "supporting_record_ids": revised.supporting_record_ids,
                    "counterevidence_ids": revised.counterevidence_ids,
                    "missing_fields": revised.missing_fields,
                    "justification": revised.justification,
                    "tool_calls_used": revised.tool_calls_used,
                }
                result.trace.append(
                    {
                        "stage": "agent_revision",
                        "agent": agent_name,
                        "revised_finding": agent_findings[agent_name],
                    }
                )

            # Re-validate after revision
            for agent_name, finding_dict in agent_findings.items():
                self.validator.validate_finding(case_id, finding_dict)

            result.agent_findings = agent_findings

        result.challenge_rounds = challenge_rounds

        # Stage 4: Apply coordinator decision rules
        decision = self._apply_decision_rules(
            case_id, agent_findings, raw_sources
        )
        result.decision = decision

        return result

    def _gather_counterevidence(
        self,
        case_id: str,
        agent_name: str,
        agent_findings: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Gather counterevidence cited by other agents for the challenge round."""
        counterevidence: list[dict[str, Any]] = []
        for other_name, finding in agent_findings.items():
            if other_name == agent_name:
                continue
            for rid in finding.get("counterevidence_ids", []):
                counterevidence.append({"record_id": rid, "source_agent": other_name})
        return counterevidence

    def _apply_decision_rules(
        self,
        case_id: str,
        agent_findings: dict[str, Any],
        raw_sources: dict[str, Any],
    ) -> Decision:
        """Apply coordinator decision rules.

        Rules (from report):
        - Supported benign: time-aligned benign mechanism (queue drops or link outage)
          without unresolved contradiction.
        - Suspected malicious: verified receipt, repeated forwarding failures under
          adequate monitoring, AND queue+link evidence does not account for failures.
          Loss percentage alone is NOT sufficient.
        - Otherwise: insufficient_evidence.
        """
        causes = {
            name: f.get("candidate_cause", "insufficient_evidence")
            for name, f in agent_findings.items()
        }

        congestion_cause = causes.get("congestion_agent", "")
        wireless_cause = causes.get("wireless_mobility_agent", "")
        pattern_cause = causes.get("forwarding_pattern_agent", "")

        # Extract raw evidence for rule checks
        watchdog = raw_sources.get("watchdog_direct_observation", {})
        packets_received = watchdog.get("packets_overheard_received", 0)
        packets_forwarded = watchdog.get("packets_overheard_forwarded", 0)
        avg_delay = watchdog.get("avg_forwarding_delay_ms", 0)
        route_changes = watchdog.get("observed_route_change_count", 0)

        # Queue/link evidence from findings
        congestion_supports_benign = congestion_cause == "honest_congestion_full_queue"
        wireless_supports_benign = wireless_cause == "honest_link_degradation"
        pattern_suggests_malicious = pattern_cause in (
            "malicious_blackhole",
            "malicious_selective_forwarding",
        )

        # Check for unresolved contradictions
        benign_votes = sum(
            1
            for c in causes.values()
            if c in ("honest_congestion_full_queue", "honest_link_degradation")
        )
        malicious_votes = sum(
            1 for c in causes.values() if c in ("malicious_blackhole", "malicious_selective_forwarding")
        )
        abstentions = sum(
            1 for c in causes.values() if c == "insufficient_evidence"
        )

        # Rule: Suspected malicious requires verified receipt + repeated failures +
        # queue/link evidence that does NOT account for failures.
        if packets_received > 0 and packets_forwarded < packets_received:
            loss_ratio = 1 - (packets_forwarded / packets_received)
            if pattern_suggests_malicious and not congestion_supports_benign and not wireless_supports_benign:
                if malicious_votes >= 1 and benign_votes == 0:
                    return Decision(
                        primary="suspected_malicious",
                        secondary_cause=pattern_cause,
                        supporting_record_ids=self._collect_supporting(agent_findings),
                        contradictory_evidence=[],
                        missing_info=[],
                        rule_applied="suspected_malicious: verified receipt + repeated failures + no benign explanation",
                        confidence="high",
                    )

        # Rule: Supported benign requires time-aligned benign mechanism without contradiction.
        if congestion_supports_benign or wireless_supports_benign:
            if malicious_votes == 0:
                return Decision(
                    primary="benign",
                    secondary_cause=congestion_cause or wireless_cause,
                    supporting_record_ids=self._collect_supporting(agent_findings),
                    contradictory_evidence=[],
                    missing_info=[],
                    rule_applied="benign: time-aligned benign mechanism without contradiction",
                    confidence="medium",
                )

        # Rule: Missing required evidence, unresolved contradictions, or unsupported outputs -> insufficient evidence.
        missing_info: list[str] = []
        if abstentions >= 2:
            missing_info.append("multiple agents abstained")
        if packets_received == 0:
            missing_info.append("no verified receipt at relay")

        return Decision(
            primary="insufficient_evidence",
            secondary_cause=None,
            supporting_record_ids=self._collect_supporting(agent_findings),
            contradictory_evidence=[],
            missing_info=missing_info,
            rule_applied="insufficient_evidence: missing required evidence or unresolved contradictions",
            confidence="low",
        )

    def _collect_supporting(self, agent_findings: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        for finding in agent_findings.values():
            ids.extend(finding.get("supporting_record_ids", []))
        # deduplicate preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for rid in ids:
            if rid not in seen:
                seen.add(rid)
                unique.append(rid)
        return unique
