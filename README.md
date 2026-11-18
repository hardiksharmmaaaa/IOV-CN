# IoV Forwarding Diagnosis System

> An evidence-grounded agentic AI system that diagnoses vehicle relay forwarding behavior in IoV/VANET networks — distinguishing malicious packet dropping (blackhole / selective forwarding) from benign degradation (congestion, queue overflow, weak links, mobility).

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000.svg)](https://flask.palletsprojects.com/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.x-orange.svg)](https://scikit-learn.org/)
[![Project Status: Complete](https://img.shields.io/badge/Status-Complete-brightgreen.svg)](docs/PROJECT_TRACKER.md)

## Interactive Table of Contents

- [Project Overview](#project-overview)
- [Live Demo (Flask Dashboard)](#live-demo-flask-dashboard)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Documentation](#documentation)
- [Demo Cases](#demo-cases)
- [Architecture at a Glance](#architecture-at-a-glance)
- [Core Developer Handoff](#core-developer-handoff)
- [Contributing](#contributing)
- [License](#license)

---

## Project Overview

**Goal:** Diagnose each relay over an observation window using only available monitoring evidence, producing one of three decisions:

| Decision | Meaning |
|----------|---------|
| `benign` | Loss explained by congestion, queue overflow, or link degradation |
| `suspected_malicious` | Repeated forwarding failures under adequate monitoring without benign explanation |
| `insufficient_evidence` | Evidence is contradictory, missing, or citations fail validation |

**Key principle:** The system never labels a vehicle malicious based on loss percentage alone. It may abstain when evidence is unclear.

**Dataset:** `Monitoring-Dataset/` — 11,000 labeled cases across 6 JSONL splits plus 2 CSVs.

---

## Live Demo (Flask Dashboard)

Run the diagnosis pipeline locally with a browser-based dashboard:

```bash
# 1. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the Flask server
python3 api.py
```

Then open in your browser:

| Page | URL | Purpose |
|------|-----|---------|
| Homepage | `http://localhost:7777/` | Project landing page |
| Diagnosis Dashboard | `http://localhost:7777/dashboard` | Case selector, agent findings, verdict |

**Demo flow:**

1. Open the dashboard at `http://localhost:7777/dashboard`.
2. Use the case selector to pick a case (e.g., `EASY_00036`).
3. Click **Run Diagnosis** to run all three specialist agents, the validator, and the coordinator.
4. Review per-agent findings, challenge rounds, coordinator verdict, and baseline comparison.
5. Switch to the **Raw Evidence** tab to inspect telemetry per case.

> **Tip:** Keep screenshots or a recording of both demo cases as backup for presentation day.

---

## Quick Start

| Step | Command | Description |
|------|---------|-------------|
| 1 | `git clone <repo-url>` | Clone the repository |
| 2 | `python3 -m venv .venv && source .venv/bin/activate` | Set up Python environment |
| 3 | `pip install -r requirements.txt` | Install Flask, scikit-learn, joblib |
| 4 | `python3 api.py` | Start the dashboard on port 7777 |
| 5 | Open `http://localhost:7777/dashboard` | Run live diagnoses |

**Smoke test (no server required):**

```bash
python3 -c "from data import EvidenceAdapter; a = EvidenceAdapter(dataset_dir='Monitoring-Dataset'); a.load_all_splits(); print(len(a.list_case_ids()), 'cases loaded')"
```

---

## Project Structure

```
IOV/
├── README.md                      # This file (interactive project entrypoint)
├── api.py                         # Flask backend + dashboard server
├── requirements.txt               # Python dependencies
├── .gitignore                     # Git ignore rules
│
├── docs/                          # All project documentation (Markdown)
│   ├── AGENTS.md                  # AI agent role instructions
│   ├── AGENT_TEAM_SPLIT.md        # Role breakdown & ownership
│   ├── architecture.md            # System components & data flow
│   ├── design.md                  # Design decisions & rationale
│   ├── PROJECT_TRACKER.md         # Task tracker with completion %
│   └── JURY_DEMO_PLAN.md          # Jury presentation & live demo script
│
├── data/                          # Evidence adapter package
│   ├── __init__.py
│   └── evidence_adapter.py        # JSONL parsing, evidence index, query tools
│
├── agents/                        # Specialist agent package
│   ├── __init__.py
│   ├── congestion_agent.py
│   ├── wireless_mobility_agent.py
│   ├── forwarding_pattern_agent.py
│   └── ml_agent.py
│
├── controller/                    # Coordinator, validator, diagnosis types
│   ├── __init__.py
│   ├── coordinator.py             # Coordinator + decision rules
│   ├── validator.py               # EvidenceValidator
│   └── diagnosis.py               # Decision & DiagnosisResult dataclasses
│
├── baselines/                     # Comparison baselines
│   ├── __init__.py
│   ├── loss_only_rule.py
│   ├── single_agent.py
│   └── evaluator.py               # Metrics computation
│
├── evaluation/                    # Ablation & masking tests
│   ├── __init__.py
│   └── ablation.py
│
├── ml/                            # Learned ML layer
│   ├── __init__.py
│   ├── features.py
│   ├── train.py
│   ├── predict.py
│   └── benchmark.py
│
├── artifacts/                     # Trained model artifacts (gitignored)
│   └── ml/
│       └── random_forest.joblib
│
├── static/                        # Dashboard frontend
│   ├── index.html                 # Diagnosis dashboard
│   └── home.html                  # Project homepage
│
├── tests/                         # Test suite
│   └── ...
│
├── Monitoring-Dataset/            # JSONL splits + CSVs (data)
│   ├── easy_test_sft.jsonl
│   ├── medium_test_sft.jsonl
│   ├── hard_stress_test_sft.jsonl
│   ├── case_heldout_test_sft.jsonl
│   ├── medium_train_sft.jsonl
│   ├── medium_validation_sft.jsonl
│   ├── label_distribution_rows.csv
│   └── malicious_severity_rows.csv
│
├── HW2_Project_Plan_and_Report.docx
├── HW2.docx
└── Final_Project_Specifications.pdf
```

---

## Documentation

All detailed documentation lives in the [`docs/`](docs/) folder:

| Document | Description | Link |
|----------|-------------|------|
| **Architecture** | System components, data flow, decision rules | [docs/architecture.md](docs/architecture.md) |
| **Design** | Design decisions, rationale, risks & limitations | [docs/design.md](docs/design.md) |
| **Agents** | AI agent role instructions & collaboration rules | [docs/AGENTS.md](docs/AGENTS.md) |
| **Team Split** | Role breakdown & ownership matrix | [docs/AGENT_TEAM_SPLIT.md](docs/AGENT_TEAM_SPLIT.md) |
| **Project Tracker** | Task tracker with completion percentages | [docs/PROJECT_TRACKER.md](docs/PROJECT_TRACKER.md) |
| **Jury Demo Plan** | Presentation script & live demo walkthrough | [docs/JURY_DEMO_PLAN.md](docs/JURY_DEMO_PLAN.md) |

---

## Demo Cases

Use these case IDs in the dashboard for a quick live demonstration:

| Case ID | Scenario | Expected Verdict |
|---------|----------|------------------|
| `EASY_00036` | Clear blackhole — relay received 84 packets, forwarded 14 (~83% loss) | `suspected_malicious` |
| `EASY_00033` | Low observability / ambiguous monitoring — ~34% loss | `insufficient_evidence` (after challenge round) |

**How to demo:**

1. Start the server: `python3 api.py`
2. Open `http://localhost:7777/dashboard`
3. Search for the case ID in the selector
4. Run diagnosis and observe the verdict, challenge rounds, and baseline comparison

---

## Architecture at a Glance

```
JSONL Dataset ─────▶ Evidence Adapter ─────▶ Evidence Index
                                           │
                                           ▼
                              ┌──────────────────────┐
                              │     Coordinator      │
                              └──────────┬───────────┘
                                         │
           ┌───────────────┬─────────────┼─────────────┐
             Congestion   Wireless     Forwarding     (ML Agent)
             Agent        Mobility     Pattern        (advisory)
             (2 tool calls)(2 tool calls) (2 tool calls)
                                         │
                              ┌──────────┴───────────┐
                              │   Evidence Validator │
                              └──────────┬───────────┘
                                         │
                              ┌──────────▼───────────┐
                              │   Diagnosis Result   │
                              │ (verdict + trace)    │
                              └──────────────────────┘
```

Read full details: [docs/architecture.md](docs/architecture.md)

---

## Core Developer Handoff

| Command | Purpose |
|---------|---------|
| `python3 api.py` | Start Flask dashboard on `http://localhost:7777` |
| `python -m ml.train` | Train the ML classifier (Random Forest default) |
| `python -m ml.benchmark` | Run baseline vs. hybrid comparison |
| `python3 -c "from baselines import ..."` | Run baselines comparison |

**Key files to touch:**

- `controller/coordinator.py` — decision rules & challenge round
- `controller/validator.py` — evidence validation
- `agents/*.py` — specialist agents
- `data/evidence_adapter.py` — evidence parsing & index
- `api.py` — Flask backend
- `static/index.html` — dashboard frontend

---

## Contributing

1. Fork the repo and create a feature branch from `prod`.
2. Make your changes. Agents must not edit each other's owned files without coordination (see [docs/AGENTS.md](docs/AGENTS.md)).
3. Update `docs/PROJECT_TRACKER.md` with task completion percentages.
4. Test end-to-end: run the dashboard and verify a diagnosis completes.
5. Open a pull request.

---

<div align="center">
  <sub>IoV Forwarding Diagnosis System — Computer Networks Course Project</sub>
</div>
