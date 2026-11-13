# Agents — Project Instructions

This document contains instructions for every AI agent role working on the IoV Forwarding Diagnosis project. Each agent owns specific files and deliverables.

## Project Overview

**Goal:** Build an evidence-grounded agentic AI system that diagnoses vehicle relay forwarding behavior in IoV/VANET networks. The system distinguishes malicious packet dropping (blackhole / selective forwarding) from benign degradation (congestion, queue overflow, weak links, mobility) and avoids unfairly blaming honest vehicles.

**Dataset:** `Monitoring-Dataset/` — 11,000 labeled cases across 6 JSONL splits (easy, medium, hard, heldout, train, validation) plus 2 CSVs.

**Key Principle:** The system may abstain (`insufficient_evidence`) when evidence is unclear. It never classifies a node as malicious based on loss percentage alone.

---

## Agent Roles

### Core Researcher
**Owns:** Dataset schema analysis, baselines, evaluation, ablation studies, metrics.

**Responsibilities:**
- Analyze `Monitoring-Dataset/` JSONL schema and field mappings
- Implement `baselines/loss_only_rule.py` and `baselines/single_agent.py`
- Implement `baselines/evaluator.py` (FAR, MDR, coverage, abstention, precision, macro F1)
- Implement `evaluation/ablation.py` (no challenge round, no abstention, evidence masking 10/30/50%)
- Choose loss threshold on development data, freeze before testing
- Report tradeoffs, not just accuracy

**Deliverables:** `baselines/`, `evaluation/`, evaluation results.

---

### Data Engineer
**Owns:** `data/` package — evidence adapter, case construction, evidence index.

**Responsibilities:**
- Parse JSONL monitoring files into `Case` objects
- Flatten `raw_sources` into immutable `EvidenceRecord` objects with IDs like `REC_000001`
- Group observations by relay (monitored_node) and time window
- Expose read-only query tools: `get_queue_evidence`, `get_link_evidence`, `get_forwarding_pattern`, `get_mobility_evidence`
- Build evidence index for the validator
- Never invent or interpret missing fields as zero

**Deliverables:** `data/evidence_adapter.py`, `data/__init__.py`.

---

### AI Agent Dev — Congestion Specialist
**Owns:** `agents/congestion_agent.py`

**Responsibilities:**
- Examine queue occupancy, queue-drop events, offered load, forwarding delay
- Hypothesis: congestion or overflow explains observed losses
- Make at most 2 read-only tool calls in first pass
- Return structured `CongestionFinding` (candidate_cause, supporting_record_ids, counterevidence_ids, missing_fields, justification, confidence)
- Support one `revise()` challenge round with 1 additional tool call
- Queue occupancy >= 90% or queue drops > 0 or avg delay > 100ms → congestion hypothesis

---

### AI Agent Dev — Wireless/Mobility Specialist
**Owns:** `agents/wireless_mobility_agent.py`

**Responsibilities:**
- Examine link measurements (RSSI), retransmissions, connection changes, monitor visibility
- Hypothesis: connectivity or incomplete observation explains missing forwarding events
- Make at most 2 read-only tool calls in first pass
- Return structured `WirelessMobilityFinding`
- Support one `revise()` challenge round
- RSSI < -85 dBm or route changes >= 2 or monitor visibility < 70% → link degradation hypothesis

---

### AI Agent Dev — Forwarding-Pattern Specialist
**Owns:** `agents/forwarding_pattern_agent.py`

**Responsibilities:**
- Examine matched receive/forward events, loss sequences, flow patterns, neighboring windows
- Hypothesis: persistent or selective failures require further examination
- Make at most 2 read-only tool calls in first pass
- Return structured `ForwardingPatternFinding`
- Support one `revise()` challenge round
- Selective drop indicators → selective forwarding; persistent high loss ratio (>0.5) → blackhole

---

### AI Agent Dev — Evidence Validator
**Owns:** `controller/validator.py`

**Responsibilities:**
- Validate agent findings: schema, cited record IDs exist, records belong to the case, numeric claims match records
- Allow one formatting repair per case; persistent failure → abstention
- Do not prove the entire explanation correct, only that citations are valid

**Deliverables:** `controller/validator.py` (`EvidenceValidator` class).

---

### Core Developer
**Owns:** `controller/` package — coordinator, decision rules, diagnosis result types.

**Responsibilities:**
- Implement `Coordinator.diagnose()`: run all 3 agents, validate findings, run bounded challenge round on conflict, apply decision rules
- Decision rules:
  - **Suspected malicious:** verified receipt + repeated forwarding failures under adequate monitoring + queue/link evidence does NOT account for failures. Loss percentage alone is NOT sufficient.
  - **Benign:** time-aligned benign mechanism (queue drops or link outage) without unresolved contradiction.
  - **Insufficient evidence:** missing required evidence, unresolved contradictions, or unsupported outputs.
- Challenge round: when agents disagree on concrete causes, send counterevidence, allow one revision per agent, then re-apply rules
- Final integration and end-to-end testing

**Deliverables:** `controller/coordinator.py`, `controller/diagnosis.py`, `controller/validator.py`, `controller/__init__.py`.

---

### Frontend Dev
**Owns:** `demo_app.py` — Streamlit demo website.

**Responsibilities:**
- Case selector from dataset splits
- Show raw telemetry evidence per case
- Run diagnosis pipeline and display per-agent findings
- Show coordinator verdict, rule applied, challenge rounds
- Compare against baselines (loss-only, single agent)
- Run on `streamlit run demo_app.py`

**Deliverables:** `demo_app.py`.

---

### Technical Writer
**Owns:** `agents.md`, `design.md`, `architecture.md`, `PROJECT_TRACKER.md`.

**Responsibilities:**
- Maintain agent instructions (`agents.md`)
- Document design decisions and rationale (`design.md`)
- Document system components and data flow (`architecture.md`)
- Keep `PROJECT_TRACKER.md` up to date with task completion percentages

---

## Collaboration Rules

1. Agents do not edit each other's owned files without coordination.
2. Shared files (`PROJECT_TRACKER.md`, `agents.md`) are updated by the owning role only.
3. All ground-truth labels remain hidden from agents during diagnosis; used only for evaluation.
4. One formatting repair is allowed per finding; persistent validation failure → abstention.
5. Repetition requirements and numeric cutoffs are chosen on development data, then frozen.

## Commands

```bash
# Run full pipeline smoke test
python3 -c "from data import EvidenceAdapter; ..."

# Run Streamlit demo
streamlit run demo_app.py

# Run baselines comparison
python3 -c "from baselines import ..."
```
