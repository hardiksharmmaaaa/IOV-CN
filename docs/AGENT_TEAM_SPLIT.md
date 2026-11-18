# Agent Team Split — IoV Forwarding Diagnosis

This file documents how the project is divided among AI agent roles. Each agent owns specific deliverables and reports completion to `PROJECT_TRACKER.md`.

## Roles

### Core Researcher
- Dataset schema analysis and field mapping
- Baseline implementations (loss-only rule, single-agent)
- Evaluation plan: metrics, data splits, ablation studies
- Result interpretation and uncertainty reporting

### Data Engineer
- Evidence adapter: ingest JSONL, normalize timestamps, immutable record IDs
- Case construction: group observations by relay and time window
- Evidence index: queryable lookup for agents

### AI Agent Dev — Congestion Specialist
- Queue occupancy, queue-drop events, offered load, forwarding delay
- Hypothesis: congestion/overflow explains observed losses

### AI Agent Dev — Wireless/Mobility Specialist
- Link measurements, retransmissions, connection changes, monitor visibility
- Hypothesis: connectivity or incomplete observation explains missing events

### AI Agent Dev — Forwarding-Pattern Specialist
- Matched receive/forward events, loss sequences, flow patterns
- Hypothesis: persistent or selective failures require further examination

### AI Agent Dev — Evidence Validator
- Schema validation of findings
- Cited record ID existence and case membership checks
- Numeric claim verification against records
- One formatting repair allowed; persistent failure → abstention

### Core Developer
- Coordinator: decision rules (benign / suspected malicious / insufficient evidence)
- Bounded challenge round for conflicting agent outputs
- Final diagnosis pipeline integration
- End-to-end testing

### Frontend Dev
- Demo website: case selection, per-agent findings, coordinator verdict
- Visualizations: evidence charts, decision trace, metrics dashboard

### Technical Writer
- `agents.md`: instructions for all agents
- `design.md`: design decisions and rationale
- `architecture.md`: system components and data flow

## Collaboration Rules
- Agents do not edit each other's owned files without coordination.
- Shared files (`PROJECT_TRACKER.md`, `agents.md`) are updated by the owning role only.
- All ground-truth labels remain hidden from agents during diagnosis; used only for evaluation.
