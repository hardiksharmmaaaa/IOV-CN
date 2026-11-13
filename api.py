"""FastAPI backend for IoV Forwarding Diagnosis demo."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from data import EvidenceAdapter
from agents import CongestionAgent, WirelessMobilityAgent, ForwardingPatternAgent
from controller import Coordinator


app = FastAPI(title="IoV Forwarding Diagnosis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global adapter (loaded on startup)
adapter: EvidenceAdapter | None = None


class DiagnosisRequest(BaseModel):
    case_id: str


class DiagnosisResponse(BaseModel):
    case_id: str
    monitored_node: str
    window: dict[str, Any]
    decision: dict[str, Any]
    agent_findings: dict[str, Any]
    challenge_rounds: int
    trace: list[dict[str, Any]]
    ground_truth: dict[str, Any] | None = None
    baselines: dict[str, Any] | None = None


@app.on_event("startup")
async def startup():
    global adapter
    adapter = EvidenceAdapter(dataset_dir="Monitoring-Dataset")
    adapter.load_all_splits()


@app.get("/api/cases")
def list_cases():
    """List all available cases with metadata."""
    if adapter is None:
        raise HTTPException(status_code=500, detail="Adapter not initialized")
    cases = []
    for cid in adapter.list_case_ids():
        case = adapter.get_case(cid)
        gt = case.ground_truth or {}
        cases.append({
            "case_id": cid,
            "node": case.monitored_node,
            "window": case.window,
            "true_behavior": gt.get("true_behavior", "unknown"),
            "difficulty": case.difficulty,
            "generation_case": case.generation_case,
            "received": gt.get("actual_packets_received", 0),
            "forwarded": gt.get("actual_packets_forwarded", 0),
        })
    return {"cases": cases}


@app.post("/api/diagnose", response_model=DiagnosisResponse)
def diagnose(req: DiagnosisRequest):
    """Run the full diagnosis pipeline for a case."""
    if adapter is None:
        raise HTTPException(status_code=500, detail="Adapter not initialized")

    case = adapter.get_case(req.case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {req.case_id} not found")

    evidence_tools = {
        "get_queue_evidence": adapter.get_queue_evidence,
        "get_link_evidence": adapter.get_link_evidence,
        "get_forwarding_pattern": adapter.get_forwarding_pattern,
    }

    agents = {
        "congestion_agent": CongestionAgent(),
        "wireless_mobility_agent": WirelessMobilityAgent(),
        "forwarding_pattern_agent": ForwardingPatternAgent(),
    }

    coordinator = Coordinator(
        agents=agents,
        evidence_tools=evidence_tools,
        evidence_index=adapter.get_evidence_index(),
    )

    result = coordinator.diagnose(
        case_id=case.case_id,
        monitored_node=case.monitored_node,
        window=case.window,
        raw_sources=case.raw_sources,
    )

    # Run baselines for comparison
    from baselines import LossOnlyRule, SingleAgentBaseline

    loss_only = LossOnlyRule(threshold=0.3)
    single_agent = SingleAgentBaseline()

    lo = loss_only.diagnose(case.case_id, case.raw_sources)
    sa = single_agent.diagnose(case.case_id, case.raw_sources)

    return {
        "case_id": result.case_id,
        "monitored_node": result.monitored_node,
        "window": result.window,
        "decision": {
            "primary": result.decision.primary,
            "secondary_cause": result.decision.secondary_cause,
            "supporting_record_ids": result.decision.supporting_record_ids,
            "contradictory_evidence": result.decision.contradictory_evidence,
            "missing_info": result.decision.missing_info,
            "rule_applied": result.decision.rule_applied,
            "confidence": result.decision.confidence,
        },
        "agent_findings": result.agent_findings,
        "challenge_rounds": result.challenge_rounds,
        "trace": result.trace,
        "ground_truth": case.ground_truth,
        "baselines": {
            "loss_only": {
                "primary": lo.primary,
                "loss_ratio": lo.loss_ratio,
                "threshold": lo.threshold,
                "rule_applied": lo.rule_applied,
            },
            "single_agent": {
                "primary": sa.primary,
                "secondary_cause": sa.secondary_cause,
                "confidence": sa.confidence,
                "justification": sa.justification,
            },
        },
    }


@app.get("/api/case/{case_id}/evidence")
def get_evidence(case_id: str):
    """Get raw evidence for a case."""
    if adapter is None:
        raise HTTPException(status_code=500, detail="Adapter not initialized")
    case = adapter.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return {
        "case_id": case.case_id,
        "raw_sources": case.raw_sources,
        "ground_truth": case.ground_truth,
    }


# Serve the frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7777)
