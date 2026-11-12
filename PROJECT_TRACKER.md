# Project Tracker — IoV Forwarding Diagnosis System

## Overview
- **Goal**: Evidence-grounded agentic AI system that diagnoses relay forwarding behavior in IoV networks (malicious vs benign vs insufficient evidence).
- **Dataset**: `Monitoring-Dataset/` (7 JSONL splits + 2 CSVs).
- **Status**: Planning phase.
- **Estimated duration**: 4–6 weeks part-time (~10 hrs/week) or ~3 weeks full-time.

## Agent Team Split

| Role | Responsibility |
|------|----------------|
| Core Researcher | Dataset schema analysis, baselines, evaluation design, metric definitions |
| Data Engineer | Evidence adapter, case construction, evidence index, JSONL parsing |
| AI Agent Dev (x3) | Congestion agent, Wireless/mobility agent, Forwarding-pattern agent |
| AI Agent Dev (Validator) | Evidence ID validation, numeric claim checking, schema validation |
| Core Developer | Coordinator, decision rules, bounded challenge round, final integration |
| Frontend Dev | Demo website (Streamlit/Gradio or React) |
| Technical Writer | `agents.md`, `design.md`, `architecture.md`, reports |

## Task Tracker

| # | Task | Owner | Status | % Complete | Est. Time | Notes |
|---|------|-------|--------|------------|-----------|-------|
| 1 | Repo structure & project scaffolding | Core Developer | Pending | 0% | 0.5 day | folders, git, deps |
| 2 | Dataset schema analysis & field mapping | Core Researcher | Pending | 0% | 1 day | inspect all JSONL splits |
| 3 | Evidence adapter (ingest + normalize) | Data Engineer | Pending | 0% | 2 days | read JSONL, immutable IDs, timestamps |
| 4 | Case construction & evidence index | Data Engineer | Pending | 0% | 2 days | group by relay + window |
| 5 | Congestion specialist agent | AI Agent Dev | Done | 100% | 2 days | queue, drops, offered load, delay |
| 6 | Wireless/mobility specialist agent | AI Agent Dev | Done | 100% | 2 days | RSSI, link, retransmissions, route changes |
| 7 | Forwarding-pattern specialist agent | AI Agent Dev | Done | 100% | 2 days | received/forwarded, loss sequences |
| 8 | Evidence validator | AI Agent Dev | Done | 100% | 2 days | ID existence, case membership, numeric claims |
| 9 | Coordinator & decision rules | Core Developer | Done | 100% | 3 days | benign/malicious/insufficient evidence rules |
| 10 | Bounded challenge round | Core Developer | Done | 100% | 2 days | conflict resolution, one revision round |
| 11 | Baselines (loss-only threshold, single agent) | Core Researcher | Pending | 0% | 2 days | comparison baselines |
| 12 | Evaluation framework & metrics | Core Researcher | Pending | 0% | 2 days | false accusation rate, detection rate, coverage, F1 |
| 13 | Ablation & evidence-masking tests | Core Researcher | Pending | 0% | 2 days | remove challenge, remove abstention, hide fields |
| 14 | Demo website (Streamlit/Gradio) | Frontend Dev | Pending | 0% | 3 days | case selector, agent findings, final verdict |
| 15 | Documentation (agents.md, design.md, architecture.md) | Technical Writer | In Progress | 10% | 2 days | files created, content pending |
| 16 | Final integration & end-to-end testing | Core Developer | Pending | 0% | 3 days | run pipeline end-to-end on held-out data |

## Completion Summary

- **Total planned effort**: ~30 person-days
- **Work completed**: Tasks 5–10 (agent pipeline + coordinator) + Task 15 docs files created
- **Overall project completion**: ~42%
- **Work remaining**: ~58%

### Percentage by Phase

| Phase | Tasks | Weight | Complete |
|-------|-------|--------|----------|
| Setup & Data | 1–4 | ~20% | 0% |
| Agent Pipeline | 5–10 | ~40% | 100% |
| Evaluation | 11–13 | ~20% | 0% |
| Demo & Docs | 14–15 | ~15% | 10% (docs files created) |
| Integration | 16 | ~5% | 0% |

## How to Update

Edit `PROJECT_TRACKER.md`:
- Change `Status` to `In Progress` / `Done`
- Update `% Complete` per task
- Recompute overall: sum of (task % × task weight) ÷ total weight
