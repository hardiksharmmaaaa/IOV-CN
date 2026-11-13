# Design — IoV Forwarding Diagnosis System

## Problem Statement

A relay vehicle may intentionally discard packets (blackhole or selective forwarding), but honest relays may also lose packets due to congestion, queue overflow, weak wireless links, changing connectivity, or incomplete monitoring. These explanations produce similar observed loss patterns. The task is to diagnose each relay over a defined observation window using only available evidence, producing one of three primary decisions: **benign**, **suspected malicious**, or **insufficient evidence**.

Intent cannot be proven from packet traces; "suspected malicious" means evidence supports suspicion, not proven guilt.

## Contribution

An evidence-grounded collaboration workflow for forwarding diagnosis in crowdsourced IoV networks:
- Three specialist AI agents examine different explanations for packet loss
- A deterministic coordinator checks evidence and produces a supported diagnosis or returns insufficient evidence
- Agents use restricted data-query tools, cite observed records, and challenge conflicting findings
- Agreement alone is not treated as proof (multiple agents can repeat the same mistaken claim)

## Expected Outputs

- Evidence adapter, three specialist agents, coordinator, saved diagnosis traces, evaluation notebook
- Each diagnosis identifies: relay and time window, decision, possible cause, supporting record IDs, contradictory evidence, missing information
- Scope: diagnosis from instructor-provided evidence dataset. Blockchain (payments/reputation), live smart contracts, new dataset, and full traffic simulator are out of scope.

## Specialist Agent Roles

| Agent | Evidence It Requests | Purpose |
|-------|---------------------|---------|
| Congestion | Queue occupancy, queue-drop events, offered load, forwarding delay | Determine whether congestion/overflow explains losses |
| Wireless/Mobility | Link measurements, retransmissions, connection changes, monitor visibility | Determine whether connectivity/incomplete observation explains missing events |
| Forwarding-Pattern | Matched receive/forward events, loss sequences, flow patterns, neighboring windows | Identify persistent/selective failures requiring examination |

Each agent is a role-specific instance of the same language model (or rule-based baseline), with a distinct prompt and tool access policy. The coordinator is program logic, not an additional unconstrained AI judge.

## Evidence Access & Bounded Agent Actions

- Python adapter assigns immutable IDs to records, normalizes timestamps, groups by relay and window
- Initial candidate window: 5 seconds, with 1- and 10-second sensitivity checks
- Agents may make at most 2 tool calls in first pass, choose a hypothesis, return structured finding
- Findings contain: candidate cause, supporting record IDs, counterevidence IDs, missing fields, concise justification
- Validator checks schema, cited ID existence, case membership, numeric claim matching
- One formatting repair allowed; persistent failure → abstention

## Coordination & Decision Rules

**Supported benign:** time-aligned benign mechanism (queue-drop events corresponding to losses, or documented link outage) without unresolved contradiction.

**Suspected malicious:** verified receipt at relay, repeated forwarding failures under adequate monitoring, AND queue/link evidence does not account for failures. Loss percentage alone cannot satisfy this rule.

**Challenge round:** If agents disagree, coordinator sends each conflicting agent the cited counterevidence for one challenge round. Each challenged agent may make one additional tool call and revise or retain. Coordinator then re-applies rules. Missing required evidence, unresolved contradictions, or unsupported outputs → insufficient evidence.

## System Overview (6 Stages)

1. Ingest provided evidence
2. Construct relay cases and evidence index
3. Run specialist investigations
4. Validate findings
5. Perform bounded challenge round when needed
6. Apply coordinator rules to produce auditable diagnosis

Output is advisory. Reputation/payment service could later consume it, but the project does not automatically penalize vehicles.

## Network Scenario

Source vehicle S → destination D through relay R1 (and R2 where available). Vehicles contribute forwarding services with associated reputation/payment. Local monitors/logged events provide partial observations. Diagnosis runs offline at a service with access to the dataset.

Conditions examined: normal forwarding, benign congestion, benign connectivity degradation, blackhole-like behavior, selective-forwarding-like behavior, partial visibility/mixed causes.

## Software Tools

| Tool | Planned Use |
|------|-------------|
| Python + pandas | Read files, normalize evidence, build cases, calculate summaries |
| Custom Python controller | Manage agent tool calls, validate IDs, bound rounds, apply decision rules |
| Tool-capable language model | Run specialist roles and single-agent baseline; record model ID, prompts, settings, usage |
| scikit-learn | Confusion matrices, precision, recall, F1 scores |
| Jupyter + Matplotlib | Inspect cases, reproducible evaluation, error/coverage plots |
| JSON + Git | Store structured findings and configs; version code and prompts |

## Evaluation Plan

**Dataset separation:** 70/30 dev/test split, grouped by run/trip, balanced classes where possible. Grouped cross-validation if small. Labels hidden from agents.

**Baselines:** loss-only threshold rule, single agent with same evidence/tools, proposed specialist-agent system. Equal token/tool-call budget comparison where feasible.

**Ablations:** remove challenge round, remove abstention. Evidence masking: hide 10%, 30%, 50% of fields/records with fixed seeds.

**Measurements:**
- False accusation rate (benign → suspected malicious)
- Malicious detection rate (malicious → suspected malicious)
- Coverage and abstention (by true class)
- Precision for malicious decisions, macro F1 on decided cases
- Evidence validity (cited IDs and numeric claims passing validation)
- Cost and latency (tokens, tool calls, elapsed time)

**Hypothesis supported if:** false accusations fall while malicious detection and coverage remain useful relative to baselines. Report tradeoffs, not accuracy alone.

## Key Design Decisions

1. **Plain Python agents, no external frameworks:** Zero dependencies, no API keys, works offline, reliable for demo.
2. **Deterministic coordinator:** Program logic makes final decision, not an unconstrained LLM judge.
3. **Bounded challenge round:** One revision round per agent when agents disagree; prevents infinite loops.
4. **Explicit abstention:** `insufficient_evidence` is a first-class outcome, not a failure.
5. **Loss percentage alone is insufficient:** Prevents false accusations from congestion/link issues.

## Risks & Limitations

- All three agents use the same model, so errors are not independent; agreement is not proof
- One challenge round may not resolve deep conflicts
- Dataset schema must be confirmed before coding; agent tool requirements are assumptions until validated
- Macro F1 on decided cases can look strong while masking high abstention; all-case confusion counts reported alongside
- If output feeds reputation/payment later, the benign vs. insufficient-evidence boundary needs careful downstream handling
