# Architecture — IoV Forwarding Diagnosis System

## High-Level Data Flow

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│   JSONL Dataset │─────▶│  Evidence Adapter│─────▶│ Evidence Index  │
│  (Monitoring-)  │      │  (data/adapter)  │      │  (records by    │
│   Dataset)      │      │                  │      │  case_id)       │
└─────────────────┘      └──────────────────┘      └────────┬────────┘
                                                            │
                                                            ▼
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│   Case Selector │─────▶│   Coordinator    │─────▶│  Diagnosis      │
│  (demo_app.py)  │      │  (controller/)   │      │  Result         │
│   (Streamlit)   │      │                  │      │  (verdict +     │
└─────────────────┘      └────────┬─────────┘      │   trace)        │
                                 │                  └─────────────────┘
                                 │
              ┌──────────┬───────┴───────┬──────────┐
                                 ▼         ▼         ▼
                         ┌────────┐ ┌────────┐ ┌────────┐
                         │Congest │ │Wireless│ │Forward │
                         │ion     │ │Mobility│ │Pattern │
                         │Agent   │ │Agent   │ │Agent   │
                         │(agents/│ │(agents/│ │(agents/│
                         │        │ │        │ │        │
                         └────┬───┘ └────┬───┘ └────┬───┘
                              │          │          │
                              ▼          ▼          ▼
                         Read-only   Read-only   Read-only
                         evidence    evidence    evidence
                         tools       tools       tools
```

## Component Details

### 1. Evidence Adapter (`data/evidence_adapter.py`)
- **Input:** JSONL files from `Monitoring-Dataset/`
- **Parsing:** Extracts `sample_id`, `monitored_node`, `window`, `raw_sources`, `ground_truth` from the `messages[1].content` JSON
- **Normalization:** Assigns immutable record IDs (`REC_000001`, `REC_000002`, ...), normalizes timestamps, groups by relay + window
- **Output:** `Case` objects + `EvidenceRecord` list
- **Query API:** `get_queue_evidence(case_id)`, `get_link_evidence(case_id)`, `get_forwarding_pattern(case_id)`, `get_mobility_evidence(case_id)`

### 2. Specialist Agents (`agents/`)
Three agents, each a Python class with `investigate()` and `revise()` methods:

| Agent | File | Evidence Sources | Max Tool Calls |
|-------|------|-----------------|----------------|
| CongestionAgent | `congestion_agent.py` | queue occupancy, drops, delay | 2 |
| WirelessMobilityAgent | `wireless_mobility_agent.py` | RSSI, link quality, route changes, visibility | 2 |
| ForwardingPatternAgent | `forwarding_pattern_agent.py` | received/forwarded packets, loss sequences | 2 |

Each returns a structured finding: `candidate_cause`, `supporting_record_ids`, `counterevidence_ids`, `missing_fields`, `justification`, `confidence`, `tool_calls_used`.

### 3. Evidence Validator (`controller/validator.py`)
- **Input:** Agent finding + evidence index
- **Checks:** schema completeness, cited record ID existence, case membership, numeric claim matching
- **Repair:** One formatting repair per case (drops unsupported IDs, fills missing fields)
- **Output:** `(is_valid, issues)` tuple; persistent failure → abstention

### 4. Coordinator (`controller/coordinator.py`)
- **Input:** case_id, monitored_node, window, raw_sources
- **Stages:**
  1. Run all 3 specialist agents (sequential, each with 2 tool calls max)
  2. Validate all findings (with one repair attempt)
  3. Check for agent disagreement on concrete causes
  4. If disagreement: bounded challenge round (1 revision per agent)
  5. Re-validate after revision
  6. Apply decision rules → final verdict
- **Output:** `DiagnosisResult` with `Decision`, agent findings, challenge rounds, full trace

### 5. Diagnose Result Types (`controller/diagnosis.py`)
- `Decision`: primary verdict, secondary cause, supporting records, contradictory evidence, missing info, rule applied, confidence
- `DiagnosisResult`: case ID, node, window, decision, agent findings, challenge rounds, trace

### 6. Baselines (`baselines/`)
| Baseline | File | Logic |
|----------|------|-------|
| Loss-Only Rule | `loss_only_rule.py` | suspected_malicious if loss ratio > threshold (default 0.3) |
| Single Agent | `single_agent.py` | Single generalist rule-based decision over all evidence |

### 7. Evaluator (`baselines/evaluator.py`)
- Computes: false accusation rate, malicious detection rate, coverage, abstention rate, precision, macro F1
- Confusion counts per class, abstention by class

### 8. Ablation Study (`evaluation/ablation.py`)
- Variants: full system, no challenge round, no abstention, masked 10/30/50% evidence
- Compares decisions across variants

### 9. Demo Website (`demo_app.py`)
- Streamlit app at `http://localhost:8501`
- Case selector, agent findings, coordinator verdict, baseline comparison, raw telemetry viewer

## Decision Rules (Coordinator)

```
IF packets_received > 0 AND packets_forwarded < packets_received:
    IF pattern_agent suggests malicious (blackhole/selective)
       AND NOT congestion supports benign
       AND NOT wireless supports benign
       AND malicious_votes >= 1 AND benign_votes == 0:
        → suspected_malicious (high confidence)

IF congestion supports benign OR wireless supports benign:
    IF malicious_votes == 0:
        → benign (medium confidence)

OTHERWISE:
    → insufficient_evidence (low confidence)
```

Loss percentage alone is NEVER sufficient for a malicious diagnosis.

## File Structure

```
IOV/
├── agents.md                    # Agent instructions (this project)
├── design.md                    # Design decisions & rationale
├── architecture.md              # System components & data flow
├── PROJECT_TRACKER.md           # Task tracker with completion %
├── AGENT_TEAM_SPLIT.md          # Role breakdown
├── data/
│   ├── __init__.py
│   └── evidence_adapter.py      # JSONL parsing, evidence index, query tools
├── agents/
│   ├── __init__.py
│   ├── congestion_agent.py
│   ├── wireless_mobility_agent.py
│   └── forwarding_pattern_agent.py
├── controller/
│   ├── __init__.py
│   ├── diagnosis.py             # Decision & DiagnosisResult dataclasses
│   ├── validator.py             # EvidenceValidator
│   └── coordinator.py           # Coordinator + decision rules
├── baselines/
│   ├── __init__.py
│   ├── loss_only_rule.py
│   ├── single_agent.py
│   └── evaluator.py             # Metrics computation
├── evaluation/
│   ├── __init__.py
│   └── ablation.py              # Ablation & masking tests
├── demo_app.py                  # Streamlit demo website
├── Monitoring-Dataset/          # JSONL splits + CSVs
│   ├── easy_test_sft.jsonl
│   ├── medium_test_sft.jsonl
│   ├── hard_stress_test_sft.jsonl
│   ├── case_heldout_test_sft.jsonl
│   ├── medium_train_sft.jsonl
│   ├── medium_validation_sft.jsonl
│   ├── label_distribution_rows.csv
│   └── malicious_severity_rows.csv
├── HW2_Project_Plan_and_Report.docx
├── HW2.docx
└── Final_Project_Specifications.pdf
```

## Integration Points

| From | To | Interface |
|------|----|-----------|
| Evidence Adapter | Agents | `get_*_evidence(case_id, **kwargs)` → list[dict] |
| Evidence Adapter | Validator | `get_evidence_index()` → dict[case_id, list[dict]] |
| Agents | Coordinator | `investigate(case_id, raw_sources, available_tools)` → Finding |
| Agents | Coordinator | `revise(case_id, counterevidence, raw_sources, available_tools)` → Finding |
| Validator | Coordinator | `validate_finding(case_id, finding_dict)` → (bool, issues) |
| Coordinator | Demo App | `diagnose(case_id, node, window, raw_sources)` → DiagnosisResult |
| Baselines | Evaluator | `diagnose(case_id, raw_sources)` → prediction string |

## Configuration

- Loss-only threshold: 0.3 (tuned on dev data, frozen before testing)
- Initial observation window: 5 seconds
- Max agent tool calls per pass: 2
- Max challenge rounds: 1
- Max formatting repairs per case: 1
- RSSI weak link threshold: -85 dBm
- Queue full threshold: 90% occupancy
- Persistent loss ratio threshold: 0.5

## Assumptions

1. Dataset schema matches `Monitoring-Dataset/` JSONL structure (verified by smoke test)
2. Ground truth labels are reserved for evaluation, hidden from agents
3. No blockchain, live smart contracts, or traffic simulator needed (out of scope)
4. Single language model powers all agents (errors not independent — acknowledged limitation)
5. Diagnosis is advisory; no automatic penalty to vehicles
