# IoV Forwarding Diagnosis — Jury Presentation and Live Demo Plan

## Important framing

Present this as an evidence-grounded IoV diagnosis prototype, not as a production system.

The current implementation contains deterministic Python specialist agents plus a trained, calibrated ML evidence agent. A real LLM provider, prompt-generation flow, and live tool-calling client are not implemented. Do not claim that three independent LLMs investigated the cases.

The application is also a dataset-driven demonstration, not a live VANET telemetry stream.

## 1. Opening explanation

Say:

> Our problem is not simply detecting packet loss. Packet loss can be caused by malicious forwarding, congestion, queue overflow, weak wireless links, mobility, or incomplete monitoring. Our system investigates these competing explanations and returns one of three decisions: benign, suspected malicious, or insufficient evidence.

Then explain the safety principle:

> The system never labels a vehicle malicious from loss percentage alone. If the evidence is contradictory or incomplete, it abstains.

The project goal is documented in [`design.md`](design.md).

## 2. Architecture explanation

Use this flow:

```text
JSONL monitoring case
        ↓
Evidence Adapter
        ↓
Case + immutable evidence records
        ↓
Three deterministic specialists + learned ML agent
        ↓
Evidence Validator
        ↓
Coordinator
        ↓
Optional challenge round
        ↓
Final diagnosis + evidence trace
        ↓
Flask dashboard
```

Explain each stage:

1. The dataset contains monitoring cases from an IoV relay scenario.
2. The evidence adapter parses each JSONL record into a normalized `Case`.
3. Raw observations become immutable records such as `REC_000001`.
4. Three specialists investigate different explanations and the ML agent scores learned telemetry patterns.
5. The validator checks whether cited evidence belongs to the case.
6. The coordinator applies hybrid safety rules.
7. If agents disagree, one bounded challenge round is allowed.
8. The dashboard displays the result, reasoning, baselines, and trace.

The learned model is trained offline with `python -m ml.train`. Random Forest is
the default serving artifact; Logistic Regression is retained as a comparison
model and can be selected with `IOV_ML_MODEL`.

Refer to [`architecture.md`](architecture.md).

## 3. Three specialist agents

### Congestion Agent

It examines:

- queue occupancy
- queue drops
- forwarding delay
- forwarding evidence

Current prototype thresholds include:

- queue occupancy at least 90%
- queue drops greater than 0
- delay greater than 100 ms

Its question is:

> Could the packet loss be explained by the relay being overloaded?

### Wireless/Mobility Agent

It examines:

- RSSI
- route changes
- retransmissions or link information
- monitor visibility

Current thresholds include:

- RSSI below -85 dBm
- route changes at least 2
- visibility below 70%

Its question is:

> Could packets be missing because the wireless link or observation process was unreliable?

### Forwarding-Pattern Agent

It examines:

- packets received
- packets forwarded
- loss sequences
- selective-drop indicators

Current logic identifies:

- selective forwarding if a selective-drop indicator exists
- blackhole-like behavior if loss exceeds 50% with sufficient received traffic

Its question is:

> Does the relay repeatedly receive packets but fail to forward them?

The implementations are in [`agents/`](agents/).

## 4. Coordinator rules

Say:

> The agents do not vote blindly. The coordinator applies explicit evidence rules.

### Suspected malicious

Requires:

- the relay demonstrably received packets
- forwarding failures are repeated
- forwarding-pattern evidence indicates malicious behavior
- queue or wireless evidence does not explain the loss

### Benign

Requires:

- a time-aligned benign mechanism such as queue overflow or link degradation
- no unresolved malicious contradiction

### Insufficient evidence

Returned when:

- required evidence is missing
- agents remain contradictory
- evidence citations are invalid
- the system cannot make a defensible decision

Key sentence:

> Insufficient evidence is a valid safety decision, not a system failure.

The coordinator is in [`controller/coordinator.py`](controller/coordinator.py).

## 5. Live demonstration plan

Start the application and open:

```text
http://localhost:7777/
http://localhost:7777/dashboard
```

The dashboard currently behaves as an evaluation dashboard. It exposes the local dataset and ground-truth information for comparison. For a production interface, only test or held-out cases should be shown and the ground-truth label should remain hidden until after diagnosis.

### Demonstration case 1: clear malicious behavior

Search for:

```text
EASY_00036
```

This is the `clear_blackhole` case.

Say:

> This relay received 84 packets and forwarded only 14, producing approximately 83.3% loss. The forwarding-pattern specialist identifies persistent blackhole-like behavior. The other specialists do not find a strong queue or link explanation. Therefore the coordinator returns suspected malicious.

Show:

- the three agent cards
- the final verdict
- confidence
- rule applied
- supporting evidence
- baseline comparison
- raw telemetry

Then say:

> This is not malicious merely because the loss is high. The decision is supported because receipt was verified, forwarding failure was persistent, and benign explanations were not supported.

### Demonstration case 2: challenge mode and abstention

Search for:

```text
EASY_00033
```

This is the `low_observability_no_confirmation` case.

It has approximately 34.2% packet loss, so the loss-only baseline may suspect malicious behavior.

Before running it, say:

> This case is deliberately ambiguous. A loss-only rule may accuse the relay, but the full system must examine whether the monitoring and wireless evidence are reliable.

Explain the initial findings:

- Congestion Agent: insufficient evidence
- Wireless/Mobility Agent: benign link degradation
- Forwarding-Pattern Agent: malicious blackhole

Then point to the challenge section and say:

> Because the agents disagree on concrete causes, the coordinator triggers one bounded challenge round.

Explain the challenge process:

1. The coordinator detects disagreement.
2. Each agent gets one additional read-only evidence check.
3. Each agent either revises or retains its finding.
4. The coordinator applies the decision rules again.
5. Because contradictory explanations remain, the system abstains.

Expected final result:

```text
insufficient_evidence
```

Key explanation:

> The challenge round does not force agreement. Its purpose is to test whether the disagreement can be resolved. If it cannot, the safest output is insufficient evidence.

The challenge behavior is displayed in [`static/index.html`](static/index.html).

Avoid using `CASEHELDOUT_00002` as the main demo case unless you specifically want to discuss borderline behavior; the current prototype produces a benign result for a case whose label is uncertain.

## 6. Baseline explanation

The dashboard compares three approaches.

### Loss-only rule

Configured with a 30% loss threshold.

Say:

> This baseline is intentionally simple. It demonstrates the danger of treating loss percentage as proof of maliciousness.

For `EASY_00033`, the loss-only rule may produce a malicious suspicion while the proposed system abstains.

### Single-agent baseline

Say:

> This uses one generalist decision process instead of separating congestion, wireless, and forwarding-pattern reasoning.

### Proposed system

Say:

> The proposed system combines three focused investigations, validation, coordination, and a bounded challenge round.

The baseline implementations are in [`baselines/`](baselines/).

## 7. Validator explanation

Say:

> An agent is not trusted just because it produces a confident answer.

The validator checks:

- required finding fields
- evidence record IDs
- whether records belong to the selected case
- whether numeric claims are supported
- one formatting repair attempt

If validation still fails, the system should abstain.

This is implemented in [`controller/validator.py`](controller/validator.py).

## 8. Dataset and UI explanation

The dataset contains 11,000 cases across:

- training
- validation
- easy test
- medium test
- hard stress test
- held-out test

If the jury asks why all cases appear in the selector, say:

> This dashboard currently behaves as an evaluation dashboard, so it exposes the full local dataset. For a production diagnosis interface, I would show only test or held-out cases and hide the ground-truth label until after diagnosis.

This is an important limitation because the current UI exposes `true_behavior` before diagnosis.

## 9. What is genuinely implemented

You can confidently claim:

- JSONL dataset ingestion
- case construction
- evidence normalization
- immutable evidence records
- three specialist agents
- evidence validation
- deterministic coordinator
- bounded challenge-round path
- benign, malicious, and abstention decisions
- loss-only and single-agent baselines
- Flask dashboard
- raw evidence and diagnosis trace display
- ablation-study code structure

Describe the deterministic specialists as:

> Specialist evidence-analysis components implemented with deterministic Python logic.

Describe the learned component as:

> A supervised telemetry classifier trained offline on the training split, calibrated on validation data, and constrained by the evidence-based coordinator.

Do not say:

> Three independent LLMs investigated the case.

Also do not present numerical accuracy, FAR, MDR, or macro-F1 unless verified result files are available. The evaluation framework exists, but the dashboard does not currently provide a trustworthy final results table.

## 10. Likely jury questions and answers

### Why not use only packet loss?

> Because congestion and weak links can produce the same loss pattern. Loss is a symptom, not proof of intent.

### Why include insufficient evidence?

> In a vehicle network, incomplete observation is expected. A false accusation can unfairly affect an honest relay, so abstention is safer than guessing.

### Is malicious behavior proven?

> No. The system only reports suspected malicious behavior based on available evidence. Intent cannot be proven from packet traces alone.

### Why is the coordinator deterministic?

> It makes the final decision auditable and reproducible. The agents analyze evidence, but explicit program rules control the final verdict.

### Why only one challenge round?

> To prevent unbounded reasoning and control latency and cost. One bounded re-check is enough for this prototype.

### Is this a live network?

> No. The Flask application runs the diagnosis pipeline live against recorded monitoring cases from the dataset.

### What are the limitations?

> The current agents are heuristic rather than fully LLM-powered, the data is offline, the challenge round is bounded, and the current dashboard is more suitable for evaluation than production use.

## 11. Demo-day preparation

Create an environment and install the Flask dependency:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 api.py
```

Then test:

1. Open `/`.
2. Open `/dashboard`.
3. Search for `EASY_00036`.
4. Run the diagnosis.
5. Search for `EASY_00033`.
6. Run the diagnosis and confirm `challenge_rounds = 1`.
7. Confirm the challenge section appears.
8. Keep the raw evidence tab available.
9. Keep screenshots or a screen recording of both successful cases as backup.

Expect the dataset to take a few seconds to load and each diagnosis to take several seconds.

## 12. Closing statement

End with:

> The contribution is not simply classifying packet loss. It is structuring competing explanations, validating evidence, challenging disagreements once, and allowing the system to abstain when the evidence is not strong enough. That makes the diagnosis more cautious and auditable than a loss-only rule.

## Quick presentation timeline

| Time | Section |
|---:|---|
| 0:00–1:00 | Problem and safety principle |
| 1:00–2:30 | Architecture and data flow |
| 2:30–4:00 | Three specialist agents |
| 4:00–6:30 | `EASY_00036`: malicious case |
| 6:30–9:00 | `EASY_00033`: challenge and abstention |
| 9:00–10:00 | Baselines and validator |
| 10:00–11:00 | Limitations and future work |
| 11:00–12:00 | Questions |
