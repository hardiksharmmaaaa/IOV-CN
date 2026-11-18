"""Flask backend for the IoV Forwarding Diagnosis dashboard.

Run with::

    python3 api.py

The Flask app serves the dashboard from ``static/index.html`` and exposes the
diagnosis API consumed by that frontend.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

from agents import CongestionAgent, ForwardingPatternAgent, MLAgent, WirelessMobilityAgent
from baselines import LossOnlyRule, SingleAgentBaseline
from controller import Coordinator
from data import EvidenceAdapter


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATASET_DIR = BASE_DIR / "Monitoring-Dataset"
DEFAULT_ML_MODEL = BASE_DIR / "artifacts" / "ml" / "random_forest.joblib"

# Disable Flask's implicit static route so it cannot shadow `/api/*` routes.
# The catch-all frontend route below serves the dashboard and its assets.
app = Flask(__name__, static_folder=None)
app.config["JSON_SORT_KEYS"] = False

# Loaded lazily so importing the Flask app does not parse the full dataset.
adapter: EvidenceAdapter | None = None


def get_adapter() -> EvidenceAdapter:
    """Return the shared evidence adapter, loading all splits once."""
    global adapter
    if adapter is None:
        adapter = EvidenceAdapter(dataset_dir=str(DATASET_DIR))
        adapter.load_all_splits()
    return adapter


def json_safe(value: Any) -> Any:
    """Convert common non-JSON-native values before sending API responses."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "isoformat") and not isinstance(value, (str, bytes)):
        try:
            return value.isoformat()
        except (AttributeError, TypeError, ValueError):
            pass
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except (AttributeError, TypeError, ValueError):
            pass
    return value


def api_error(message: str, status_code: int):
    return jsonify({"error": message}), status_code


@app.after_request
def add_cors_headers(response):
    """Allow the dashboard to call the API during local development."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/api/cases", methods=["GET"])
def list_cases():
    """List all available cases with metadata for the dashboard selector."""
    try:
        current_adapter = get_adapter()
        cases = []
        for case_id in current_adapter.list_case_ids():
            case = current_adapter.get_case(case_id)
            ground_truth = case.ground_truth or {}
            cases.append(
                {
                    "case_id": case_id,
                    "node": case.monitored_node,
                    "window": case.window,
                    "true_behavior": ground_truth.get("true_behavior", "unknown"),
                    "difficulty": case.difficulty,
                    "generation_case": case.generation_case,
                    "received": ground_truth.get("actual_packets_received", 0),
                    "forwarded": ground_truth.get("actual_packets_forwarded", 0),
                }
            )
        return jsonify(json_safe({"cases": cases}))
    except Exception as exc:
        app.logger.exception("Failed to load cases")
        return api_error(f"Unable to load cases: {exc}", 500)


@app.route("/api/diagnose", methods=["POST"])
def diagnose():
    """Run the full specialist-agent diagnosis pipeline for one case."""
    payload = request.get_json(silent=True) or {}
    case_id = payload.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        return api_error("case_id is required", 400)

    try:
        current_adapter = get_adapter()
        case = current_adapter.get_case(case_id)
        if case is None:
            return api_error(f"Case {case_id} not found", 404)

        evidence_tools = {
            "get_queue_evidence": current_adapter.get_queue_evidence,
            "get_link_evidence": current_adapter.get_link_evidence,
            "get_forwarding_pattern": current_adapter.get_forwarding_pattern,
        }
        agents = {
            "congestion_agent": CongestionAgent(),
            "wireless_mobility_agent": WirelessMobilityAgent(),
            "forwarding_pattern_agent": ForwardingPatternAgent(),
        }
        ml_model_path = Path(os.getenv("IOV_ML_MODEL", str(DEFAULT_ML_MODEL)))
        ml_agent = MLAgent(str(ml_model_path)) if ml_model_path.exists() else None
        coordinator = Coordinator(
            agents=agents,
            evidence_tools=evidence_tools,
            evidence_index=current_adapter.get_evidence_index(),
            ml_agent=ml_agent,
        )
        result = coordinator.diagnose(
            case_id=case.case_id,
            monitored_node=case.monitored_node,
            window=case.window,
            raw_sources=case.raw_sources,
        )

        loss_only = LossOnlyRule(threshold=0.3).diagnose(
            case.case_id, case.raw_sources
        )
        single_agent = SingleAgentBaseline().diagnose(
            case.case_id, case.raw_sources
        )

        response = {
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
                    "primary": loss_only.primary,
                    "loss_ratio": loss_only.loss_ratio,
                    "threshold": loss_only.threshold,
                    "rule_applied": loss_only.rule_applied,
                },
                "single_agent": {
                    "primary": single_agent.primary,
                    "secondary_cause": single_agent.secondary_cause,
                    "confidence": single_agent.confidence,
                    "justification": single_agent.justification,
                },
            },
        }
        return jsonify(json_safe(response))
    except Exception as exc:
        app.logger.exception("Diagnosis failed for case %s", case_id)
        return api_error(f"Diagnosis failed: {exc}", 500)


@app.route("/api/case/<path:case_id>/evidence", methods=["GET"])
def get_evidence(case_id: str):
    """Return raw telemetry evidence for one case."""
    try:
        current_adapter = get_adapter()
        case = current_adapter.get_case(case_id)
        if case is None:
            return api_error(f"Case {case_id} not found", 404)
        return jsonify(
            json_safe(
                {
                    "case_id": case.case_id,
                    "raw_sources": case.raw_sources,
                    "ground_truth": case.ground_truth,
                }
            )
        )
    except Exception as exc:
        app.logger.exception("Evidence lookup failed for case %s", case_id)
        return api_error(f"Evidence lookup failed: {exc}", 500)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path: str):
    """Serve the homepage, dashboard, and static assets."""
    if not path:
        return send_from_directory(STATIC_DIR, "home.html")
    if path == "dashboard":
        return send_from_directory(STATIC_DIR, "index.html")
    requested = STATIC_DIR / path
    if path and requested.is_file():
        return send_from_directory(STATIC_DIR, path)
    return send_from_directory(STATIC_DIR, "index.html")


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "7777")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
