"""Streamlit demo app for IoV Forwarding Diagnosis System.

Run with: streamlit run demo_app.py
"""

from __future__ import annotations

import json
import streamlit as st
from pathlib import Path

from data import EvidenceAdapter
from agents import CongestionAgent, WirelessMobilityAgent, ForwardingPatternAgent
from controller import Coordinator
from baselines import LossOnlyRule, SingleAgentBaseline, BaselineEvaluator
from evaluation import AblationStudy

st.set_page_config(
    page_title="IoV Forwarding Diagnosis — Agentic AI Watchdog",
    page_icon="🚗",
    layout="wide",
)

# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #
if "adapter" not in st.session_state:
    st.session_state.adapter = None
if "cases" not in st.session_state:
    st.session_state.cases = []
if "selected_case" not in st.session_state:
    st.session_state.selected_case = None
if "diagnosis_result" not in st.session_state:
    st.session_state.diagnosis_result = None


@st.cache_data(show_spinner=False)
def load_dataset(split_file: str = "easy_test_sft.jsonl"):
    """Load a dataset split and return adapter + case list."""
    adapter = EvidenceAdapter(dataset_dir="Monitoring-Dataset")
    adapter.load_split(split_file)
    cases = []
    for cid in adapter.list_case_ids():
        case = adapter.get_case(cid)
        cases.append({
            "case_id": cid,
            "node": case.monitored_node,
            "true_behavior": case.ground_truth["true_behavior"],
            "difficulty": case.difficulty,
            "generation_case": case.generation_case,
            "received": case.ground_truth["actual_packets_received"],
            "forwarded": case.ground_truth["actual_packets_forwarded"],
        })
    return adapter, cases


def run_diagnosis(case_id: str, raw_sources: dict, window: dict, monitored_node: str):
    """Run the full diagnosis pipeline."""
    evidence_tools = {
        "get_queue_evidence": st.session_state.adapter.get_queue_evidence,
        "get_link_evidence": st.session_state.adapter.get_link_evidence,
        "get_forwarding_pattern": st.session_state.adapter.get_forwarding_pattern,
    }
    agents = {
        "congestion_agent": CongestionAgent(),
        "wireless_mobility_agent": WirelessMobilityAgent(),
        "forwarding_pattern_agent": ForwardingPatternAgent(),
    }
    coordinator = Coordinator(
        agents=agents,
        evidence_tools=evidence_tools,
        evidence_index=st.session_state.adapter.get_evidence_index(),
    )
    result = coordinator.diagnose(
        case_id=case_id,
        monitored_node=monitored_node,
        window=window,
        raw_sources=raw_sources,
    )
    return result


def run_baselines(case_id: str, raw_sources: dict):
    """Run both baselines."""
    loss_only = LossOnlyRule(threshold=0.3)
    single_agent = SingleAgentBaseline()

    lo = loss_only.diagnose(case_id, raw_sources)
    sa = single_agent.diagnose(case_id, raw_sources)

    return {
        "loss_only": lo,
        "single_agent": sa,
    }


def format_decision_badge(decision: str) -> str:
    """Return HTML badge for decision."""
    colors = {
        "benign": "#28a745",
        "suspected_malicious": "#dc3545",
        "insufficient_evidence": "#ffc107",
    }
    color = colors.get(decision, "#6c757d")
    label = decision.replace("_", " ").title()
    return f'<span style="background-color:{color};color:white;padding:4px 12px;border-radius:12px;font-weight:bold;">{label}</span>'


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.title("🚗 IoV Forwarding Diagnosis — Agentic AI Watchdog")
st.markdown(
    "**Collaborative AI Diagnosis of Vehicle Forwarding Problems**  \n"
    "Distinguishes malicious packet dropping (blackhole/selective forwarding) "
    "from benign network degradation (congestion, weak links, mobility)."
)

# --------------------------------------------------------------------------- #
# Sidebar: Dataset & Case Selection
# --------------------------------------------------------------------------- #
st.sidebar.header("📊 Dataset")

split_file = st.sidebar.selectbox(
    "Select dataset split",
    ["easy_test_sft.jsonl", "medium_test_sft.jsonl", "hard_stress_test_sft.jsonl",
     "case_heldout_test_sft.jsonl", "medium_validation_sft.jsonl"],
    index=0,
)

if st.sidebar.button("Load Dataset") or st.session_state.adapter is None:
    with st.spinner("Loading dataset..."):
        adapter, cases = load_dataset(split_file)
        st.session_state.adapter = adapter
        st.session_state.cases = cases
    st.sidebar.success(f"Loaded {len(cases)} cases")

if st.session_state.adapter is None:
    st.info("Please load a dataset from the sidebar to begin.")
    st.stop()

adapter: EvidenceAdapter = st.session_state.adapter
cases = st.session_state.cases

# Filter options
behavior_filter = st.sidebar.multiselect(
    "Filter by behavior class",
    options=sorted(set(c["true_behavior"] for c in cases)),
    default=sorted(set(c["true_behavior"] for c in cases)),
)

filtered_cases = [c for c in cases if c["true_behavior"] in behavior_filter]

st.sidebar.markdown(f"**{len(filtered_cases)} cases** matching filters")

case_options = {f"{c['case_id']} ({c['node']}) — {c['true_behavior']}": c for c in filtered_cases}
selected_label = st.sidebar.selectbox("Select case", options=list(case_options.keys()))
selected_case = case_options[selected_label]

# --------------------------------------------------------------------------- #
# Load case details
# --------------------------------------------------------------------------- #
case = adapter.get_case(selected_case["case_id"])
raw_sources = case.raw_sources
watchdog = raw_sources.get("watchdog_direct_observation", {})
nnq = raw_sources.get("node_or_neighbor_query", {})
pm = raw_sources.get("protocol_message", {})

# --------------------------------------------------------------------------- #
# Main: Case Overview
# --------------------------------------------------------------------------- #
st.header(f"📋 Case: {selected_case['case_id']}")
st.markdown(f"**Monitored Node:** {selected_case['node']}  |  **Window:** {case.window['start_s']}s–{case.window['end_s']}s")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("True Behavior", selected_case["true_behavior"].replace("_", " ").title())
with col2:
    st.metric("Packets Received", selected_case["received"])
with col3:
    st.metric("Packets Forwarded", selected_case["forwarded"])
with col4:
    loss_ratio = 1 - (selected_case["forwarded"] / selected_case["received"]) if selected_case["received"] > 0 else 0
    st.metric("Loss Ratio", f"{loss_ratio:.1%}")

# --------------------------------------------------------------------------- #
# Run Diagnosis
# --------------------------------------------------------------------------- #
if st.button("🔍 Run Diagnosis", type="primary"):
    with st.spinner("Running specialist agents and coordinator..."):
        result = run_diagnosis(
            case_id=case.case_id,
            raw_sources=raw_sources,
            window=case.window,
            monitored_node=case.monitored_node,
        )
        baselines = run_baselines(case.case_id, raw_sources)
        st.session_state.diagnosis_result = {
            "coordinator": result,
            "baselines": baselines,
        }

# --------------------------------------------------------------------------- #
# Display Results
# --------------------------------------------------------------------------- #
if st.session_state.diagnosis_result:
    res = st.session_state.diagnosis_result
    coord = res["coordinator"]
    bl = res["baselines"]

    st.header("🏥 Diagnosis Results")

    # Final verdict
    st.subheader("Final Verdict (Coordinator)")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(format_decision_badge(coord.decision.primary), unsafe_allow_html=True)
    with col2:
        st.metric("Secondary Cause", coord.decision.secondary_cause or "—")
    with col3:
        st.metric("Confidence", coord.decision.confidence.title())

    st.markdown(f"**Rule Applied:** {coord.decision.rule_applied}")
    st.markdown(f"**Challenge Rounds:** {coord.challenge_rounds}")
    if coord.decision.missing_info:
        st.markdown(f"**Missing Info:** {', '.join(coord.decision.missing_info)}")

    # Agent findings
    st.subheader("🤖 Specialist Agent Findings")
    agent_cols = st.columns(3)

    agent_names = [
        ("congestion_agent", "Congestion Agent", "Queue / Drop / Delay"),
        ("wireless_mobility_agent", "Wireless/Mobility Agent", "RSSI / Link / Mobility"),
        ("forwarding_pattern_agent", "Forwarding-Pattern Agent", "Received / Forwarded / Loss"),
    ]

    for col, (key, name, subtitle) in zip(agent_cols, agent_names):
        with col:
            f = coord.agent_findings.get(key, {})
            st.markdown(f"### {name}")
            st.caption(subtitle)
            cause = f.get("candidate_cause", "unknown").replace("_", " ").title()
            conf = f.get("confidence", "low").title()
            st.markdown(format_decision_badge(cause.lower().replace(" ", "_") if cause != "Unknown" else "insufficient_evidence"), unsafe_allow_html=True)
            st.markdown(f"**Confidence:** {conf}")
            st.markdown(f"**Justification:** {f.get('justification', '—')}")
            st.markdown(f"**Supporting Records:** {len(f.get('supporting_record_ids', []))}")
            st.markdown(f"**Counterevidence:** {len(f.get('counterevidence_ids', []))}")
            st.markdown(f"**Missing Fields:** {', '.join(f.get('missing_fields', [])) or 'None'}")
            st.markdown(f"**Tool Calls:** {f.get('tool_calls_used', 0)}")

    # Challenge round
    if coord.challenge_rounds > 0:
        st.subheader("⚔️ Challenge Round")
        st.info("Agents disagreed on the cause. A bounded challenge round was triggered — each agent reviewed counterevidence and could revise its finding.")
        for trace in coord.trace:
            if trace.get("stage") == "challenge_round":
                st.json(trace)
            elif trace.get("stage") == "agent_revision":
                st.json(trace)

    # Baselines comparison
    st.subheader("📈 Baseline Comparison")
    bl_cols = st.columns(3)

    lo = bl["loss_only"]
    sa = bl["single_agent"]

    with bl_cols[0]:
        st.markdown("### Loss-Only Rule")
        st.markdown(format_decision_badge(lo.primary), unsafe_allow_html=True)
        st.caption(f"Loss ratio: {lo.loss_ratio:.2f} vs threshold: {lo.threshold}")
        st.caption(lo.rule_applied)

    with bl_cols[1]:
        st.markdown("### Single Agent")
        st.markdown(format_decision_badge(sa.primary), unsafe_allow_html=True)
        st.caption(sa.justification)

    with bl_cols[2]:
        st.markdown("### Proposed System")
        st.markdown(format_decision_badge(coord.decision.primary), unsafe_allow_html=True)
        st.caption(coord.decision.rule_applied)

    # Raw evidence
    with st.expander("📡 Raw Telemetry Evidence"):
        st.json(raw_sources)

    # Ground truth
    st.info(f"**Ground Truth:** {case.ground_truth['true_behavior']} (generation case: {case.generation_case})")

# --------------------------------------------------------------------------- #
# Footer
# --------------------------------------------------------------------------- #
st.markdown("---")
st.markdown(
    "**IoV Forwarding Diagnosis System** — Assignment 2 / Final Project  \n"
    "COSC 630/788 Advanced Computer Networks | Track 1: Collaborative Diagnosis Agents"
)
