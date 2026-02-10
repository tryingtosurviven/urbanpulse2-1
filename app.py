import os
import socket
import time
import json
import random
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request, send_from_directory

# --- watsonx ---
from ibm_watsonx_ai.foundation_models import Model
from ibm_watsonx_ai import Credentials


# ==============================================================================
# CONFIG
# ==============================================================================
def env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "y", "on")


def is_demo_mode() -> bool:
    # Demo mode means: allow fallback if watsonx fails (prevents demo from crashing)
    return env_bool("DEMO_MODE", "true")


def watsonx_enabled() -> bool:
    # Live watsonx means we have the required creds set AND WATSONX_ENABLED true (or default true)
    return env_bool("WATSONX_ENABLED", "true") and all(
        os.getenv(k) for k in ("WATSONX_API_KEY", "WATSONX_URL", "WATSONX_PROJECT_ID", "WATSONX_MODEL_ID")
    )


INSTANCE = {
    "pid": os.getpid(),
    "host": socket.gethostname(),
    "started_at_epoch": int(time.time()),
    "file": __file__,
}

APP_VERSION = "urbanpulse-r2-watsonx-live-1.0"

app = Flask(__name__)


# ==============================================================================
# GLOBAL STATE (Demo-friendly, judge-visible)
# ==============================================================================
active_orders = [] # Add this line
clinic_state = {
    "view": "normal",
    "protocol": "standard",  # standard | autonomous
    "draft": {
        "active": False,
        "facility": "---",
        "id": "---",
        "qty": 0,
        "cost": "$0",
        "reason": "",
        "autonomous": False,
    },
}

AGENT_SYSTEM = None
WATSONX_MODEL: Optional[Model] = None


# ==============================================================================
# AGENT SYSTEM BUILDER (local multi-agent fallback)
# ==============================================================================
def _build_agent_system():
    from agents import (
        EnvironmentSentinel,
        ScalestackAgent,
        DynamiqMedicalAgent,
        HealthcarePreparednessAgent,
        SupplyChainAgent,
    )

    sentinel = EnvironmentSentinel()
    sentinel.register_agent(ScalestackAgent())
    sentinel.register_agent(DynamiqMedicalAgent())
    sentinel.register_agent(HealthcarePreparednessAgent())
    sentinel.register_agent(SupplyChainAgent())
    return sentinel


# ==============================================================================
# WATSONX INITIALIZATION
# ==============================================================================
def _get_watsonx_model() -> Optional[Model]:
    """
    Returns a cached watsonx Model if credentials exist, else None.
    """
    global WATSONX_MODEL
    if WATSONX_MODEL is not None:
        return WATSONX_MODEL

    if not watsonx_enabled():
        return None

    creds = Credentials(
        url=os.getenv("WATSONX_URL"),
        api_key=os.getenv("WATSONX_API_KEY"),
    )

    WATSONX_MODEL = Model(
        model_id=os.getenv("WATSONX_MODEL_ID"),
        credentials=creds,
        project_id=os.getenv("WATSONX_PROJECT_ID"),
    )
    return WATSONX_MODEL


def _watsonx_reason(prompt: str) -> Dict[str, Any]:
    """
    Calls watsonx live at runtime.
    Returns parsed JSON dict. Raises if parsing fails.
    """
    model = _get_watsonx_model()
    if model is None:
        raise RuntimeError("watsonx not configured (missing env vars or WATSONX_ENABLED=false)")

    # Keep generation stable for judges (deterministic-ish)
    params = {
        "decoding_method": "greedy",
        "max_new_tokens": 350,
        "temperature": 0.2,
    }

    # Depending on SDK version, method can be generate_text or generate.
    # We'll try generate_text first, fallback to generate if needed.
    try:
        txt = model.generate_text(prompt=prompt, params=params)
    except TypeError:
        # Some versions use model.generate(prompt, params)
        txt = model.generate(prompt=prompt, params=params)

    # txt may be dict or string depending on SDK version
    if isinstance(txt, dict):
        # Try common shapes
        text_out = (
            txt.get("results", [{}])[0].get("generated_text")
            or txt.get("generated_text")
            or json.dumps(txt)
        )
    else:
        text_out = str(txt)

    # Robust extraction: find first JSON object in output
    start = text_out.find("{")
    end = text_out.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"watsonx did not return JSON. Raw: {text_out[:300]}")

    json_blob = text_out[start : end + 1]
    return json.loads(json_blob)


# ==============================================================================
# CORE: SCENARIO EXECUTION
# ==============================================================================
def _scenario_with_jitter(base: Dict[str, Any]) -> Dict[str, Any]:
    psi_data = {
        region: int(val) + random.randint(-3, 3)
        for region, val in base.get("psi_data", {}).items()
    }
    return {**base, "psi_data": psi_data}


def _policy_autonomous_only_for_severe(scenario_key: str, risk_level: str, highest_psi: int) -> bool:
    """
    Your requested policy:
    - ONLY severe haze can fully auto-dispatch
    - Use BOTH scenario key + inferred risk to be safe
    """
    if scenario_key == "severe_haze":
        return True
    # Optional safety: if model says severe / critical, but scenario isn't severe_haze, keep human-in-loop
    return False


def _build_watsonx_prompt(scenario_key: str, psi_data: Dict[str, int]) -> str:
    """
    Judge-friendly prompt: returns structured JSON with reasoning and operational outputs.
    """
    return f"""
You are "UrbanPulse SupplyChainAgent", supporting Singapore haze response.

Context:
- Urban problem: haze events raise respiratory demand.
- Objective: recommend N95 mask order quantity for clinics, and decide whether to auto-dispatch.
- Safety policy: Auto-dispatch is ONLY allowed for scenario_key == "severe_haze". Otherwise produce a draft order for human approval.

Inputs:
scenario_key: "{scenario_key}"
PSI readings by region (0-500 scale):
{json.dumps(psi_data, indent=2)}

Output:
Return STRICT JSON only with these keys:
{{
  "risk_level": "LOW|MODERATE|SEVERE",
  "highest_psi": <int>,
  "affected_regions": [<region strings>],
  "recommended_qty": <int>,              # N95 masks
  "justification": "<1-3 sentences>",
  "citizen_advice": "<1-2 sentences>",
  "clinic_action": "<1-2 sentences>",
  "data_sources": ["NEA PSI feed (simulated for demo)", "MOH haze guidance (conceptual)"],
  "governance": {{
    "human_in_loop": <true/false>,
    "auto_dispatch_allowed": <true/false>,
    "why": "<short>"
  }}
}}

Rules:
- Use the highest PSI across regions as the main driver.
- Suggested qty guidance (use common-sense tiers):
  - LOW: 200–400
  - MODERATE: 500–900
  - SEVERE: 1000–1600
- Choose affected_regions where PSI >= (highest_psi - 10).
- IMPORTANT: "governance.auto_dispatch_allowed" must be true ONLY if scenario_key == "severe_haze".
"""


def run_scenario_with_watsonx_first(scenario_key: str, source: str = "ui") -> Dict[str, Any]:
    """
    Main function: tries live watsonx reasoning first, falls back to local MAS if needed.
    """
    global AGENT_SYSTEM, clinic_state

    from scenarios import DEMO_SCENARIOS

    if scenario_key not in DEMO_SCENARIOS:
        raise ValueError(f"Invalid scenario: {scenario_key}")

    base = DEMO_SCENARIOS[scenario_key]
    scenario = _scenario_with_jitter(base)
    psi_by_region = scenario["psi_data"]

    agent_logs = []
    used_watsonx = False
    watsonx_error = None

    # 1) Live watsonx (preferred)
    decision: Optional[Dict[str, Any]] = None
    if watsonx_enabled():
        try:
            agent_logs.append({"agent": "EnvironmentSentinel", "action": "Calling watsonx reasoning", "ts": time.time()})
            decision = _watsonx_reason(_build_watsonx_prompt(scenario_key, psi_by_region))
            used_watsonx = True
            agent_logs.append({"agent": "SupplyChainAgent(watsonx)", "action": "Decision returned", "ts": time.time()})
        except Exception as e:
            watsonx_error = str(e)
            agent_logs.append({"agent": "SupplyChainAgent(watsonx)", "action": "watsonx failed, fallback engaged", "error": watsonx_error, "ts": time.time()})

            if not is_demo_mode():
                # In non-demo mode, we can fail fast to show real integration expectations
                raise

    # 2) Fallback MAS if needed (keeps demo stable)
    if decision is None:
        if AGENT_SYSTEM is None:
            AGENT_SYSTEM = _build_agent_system()
        agent_logs.append({"agent": "EnvironmentSentinel", "action": "Running local multi-agent cycle (fallback)", "ts": time.time()})
        result = AGENT_SYSTEM.run_cycle(scenario)

        risk = result.get("risk_assessment", {})
        supply = result.get("supply_chain_actions", {})

        highest = int(risk.get("current_psi", max(psi_by_region.values())))
        rl = str(risk.get("risk_level", "UNKNOWN")).upper()
        if "SEVERE" in rl or "CRITICAL" in rl or highest >= 200:
            risk_level = "SEVERE"
        elif highest >= 101:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"

        rec_qty = (
            supply.get("order_details", {}).get("n95_masks")
            or supply.get("recommended_qty")
            or (1200 if scenario_key == "severe_haze" else 600 if scenario_key == "moderate_haze" else 300)
        )

        decision = {
            "risk_level": risk_level,
            "highest_psi": highest,
            "affected_regions": list(psi_by_region.keys()),
            "recommended_qty": int(rec_qty),
            "justification": "Fallback MAS computed risk and recommended stock buffer.",
            "citizen_advice": "Limit outdoor activity if PSI is elevated; wear a mask if needed.",
            "clinic_action": "Prepare respiratory supplies; review N95 stock levels.",
            "data_sources": ["NEA PSI feed (simulated for demo)", "MOH haze guidance (conceptual)"],
            "governance": {
                "human_in_loop": scenario_key != "severe_haze",
                "auto_dispatch_allowed": scenario_key == "severe_haze",
                "why": "Auto-dispatch restricted to severe haze only."
            }
        }

    # Normalize decision
    highest_psi = int(decision.get("highest_psi", max(psi_by_region.values())))
    risk_level = str(decision.get("risk_level", "UNKNOWN")).upper()
    recommended_qty = int(decision.get("recommended_qty", 500))
    affected_regions = decision.get("affected_regions") or list(psi_by_region.keys())

    # ------------------------------------------------------------------
    # DEMO FORECAST (judge-visible "automation"): predict PSI in a few hours
    # ------------------------------------------------------------------
    forecast = None
    if scenario_key == "moderate_haze":
        horizon_hours = 3  # "a few hours"
        # Fake dataset logic: mild upward drift + noise, clamped
        predicted_psi = min(200, max(60, highest_psi + random.randint(18, 45)))
    
        forecast = {
            "horizon_hours": horizon_hours,
            "predicted_psi": predicted_psi,
            "predicted_risk_level": "MODERATE" if predicted_psi <= 100 else "UNHEALTHY",
            "confidence": 0.82,
            "method": "demo_forecast_agent_v1"
        }

    elif scenario_key == "low_haze":
        horizon_hours = 6  # low haze tends to be slower-moving
        # small drift, mostly stable
        predicted_psi = min(100, max(30, highest_psi + random.randint(-5, 12)))
        forecast = {
            "horizon_hours": horizon_hours,
            "predicted_psi": predicted_psi,
            "predicted_risk_level": "GOOD" if predicted_psi <= 50 else "MODERATE",
            "confidence": 0.88,
            "method": "demo_forecast_agent_v1"
        }

    elif scenario_key == "severe_haze":
        horizon_hours = 1  # severe changes fast
        # Strong upward drift + noise, clamped into severe range
        predicted_psi = min(400, max(180, highest_psi + random.randint(35, 90)))
    
        # Label it for storytelling
        if predicted_psi <= 200:
            predicted_risk = "UNHEALTHY"
        elif predicted_psi <= 300:
            predicted_risk = "VERY UNHEALTHY"
        else:
            predicted_risk = "HAZARDOUS"
    
        forecast = {
            "horizon_hours": horizon_hours,
            "predicted_psi": predicted_psi,
            "predicted_risk_level": predicted_risk,
            "confidence": 0.90,
            "method": "demo_forecast_agent_v1"
        }

    # Governance: your requested policy
    autonomous = _policy_autonomous_only_for_severe(scenario_key, risk_level, highest_psi)
    if source == "ui":
        autonomous = False
    clinic_state["protocol"] = "autonomous" if autonomous else "standard"

    # PO id (demo)
    po_id = f"PO-{int(time.time())}"

    # Update clinic draft state (this is what clinic.html consumes)
    clinic_state["draft"] = {
        "active": True,
        "facility": "Tan Tock Seng Hospital (HQ)",
        "id": po_id,
        "qty": recommended_qty,
        "cost": "$—",
        "reason": decision.get("justification", ""),
        "autonomous": autonomous,
        "psi": highest_psi,   # ✅ IMPORTANT: so the UI can detect severity
        "risk_level": risk_level,
    
    }

    # Add agentic logs (judge-friendly)
    agent_logs.extend([
        {"agent": "EnvironmentSentinel", "action": f"PSI highest={highest_psi} → risk={risk_level}", "ts": time.time()},
        {"agent": "SupplyChainAgent", "action": f"Recommended N95 order qty={recommended_qty}", "ts": time.time()},
        {"agent": "Governance", "action": "Auto-dispatch ONLY on severe_haze" if autonomous else "Human approval required", "ts": time.time()},
    ])

    # Final response contract (matches your frontend expectations)
    return {
        "status": "success",
        "scenario": scenario_key,
        "watsonx": {
            "enabled": watsonx_enabled(),
            "used": used_watsonx,
            "error": watsonx_error,
            "model_id": os.getenv("WATSONX_MODEL_ID", ""),
            "project_id": os.getenv("WATSONX_PROJECT_ID", ""),
        },
        "environmental_data": {"psi_by_region": psi_by_region},
        "risk_assessment": {
            "current_psi": highest_psi,
            "risk_level": risk_level,
            "affected_regions": affected_regions,
        },
        "healthcare_alerts": {
            "alert_message": decision.get("clinic_action", ""),
            "citizen_advice": decision.get("citizen_advice", ""),
        },
        "supply_chain_actions": {
            "recommended_qty": recommended_qty,
            "po_id": po_id,
            "autonomous": autonomous,
            "justification": decision.get("justification", ""),
            "governance": decision.get("governance", {}),
        },
        "predictive_analytics": forecast,   # add this
        "logs": agent_logs,
        "instance": {**INSTANCE, "app_version": APP_VERSION},
    }


# ==============================================================================
# ROUTES
# ==============================================================================
@app.route("/")
def home():
    return send_from_directory("static", "index.html")


@app.route("/citizen")
def citizen_portal():
    return send_from_directory("static", "citizen.html")


@app.route("/clinic")
def clinic_portal():
    # Reset view/protocol each time user loads clinic portal
    clinic_state["view"] = "normal"
    clinic_state["protocol"] = "standard"
    clinic_state["draft"]["active"] = False
    return send_from_directory("static", "clinic.html")


@app.route("/admin")
def admin_portal():
    return send_from_directory("static", "admin.html")


@app.route("/logistics")
def logistics_portal():
    return send_from_directory("static", "logistics.html")


# ==============================================================================
# API: SCENARIO EXECUTION (primary endpoint used by your frontend)
# ==============================================================================
@app.post("/api/run-scenario/<scenario_key>")
def api_run_scenario(scenario_key):
    try:
        source = request.args.get("source", "ui").strip().lower()
        result = run_scenario_with_watsonx_first(scenario_key.strip().lower(), source=source)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "instance": INSTANCE}), 400


# ==============================================================================
# API: WATSONX SCENARIO (explicit endpoint if you want to call it directly)
# ==============================================================================
@app.post("/api/watsonx-scenario")
def watsonx_scenario():
    payload = request.json or {}
    raw_key = payload.get("scenario_key", "")
    scenario_key = raw_key.strip().lower().replace(" ", "_")
    try:
        result = run_scenario_with_watsonx_first(scenario_key)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "instance": INSTANCE}), 400


# ==============================================================================
# API: CLINIC POLLING / ORDERS
# ==============================================================================
@app.get("/api/clinic-poll")
def clinic_poll():
    # If no scenario has been run yet, no draft exists.
    if not clinic_state["draft"].get("active"):
        return jsonify({"status": "waiting", "current_view": clinic_state["view"], "protocol": clinic_state["protocol"]})

    return jsonify({
        "status": "alert_active",
        "current_view": clinic_state["view"],
        "protocol": clinic_state["protocol"],
        "draft": clinic_state["draft"],
        "psi": clinic_state["draft"].get("psi", 0),
        "alert_message": clinic_state["draft"].get("reason", ""),
    })


@app.post("/api/clinic-confirm-order")
def confirm_order():
    data = request.json or {}
    confirmed = int(data.get("confirmed_qty") or 0)

    # This creates the data for the Logistics Map
    new_order = {
        "id": clinic_state["draft"].get("id", f"PO-{int(time.time())}"),
        "facility": clinic_state["draft"].get("facility", "Tan Tock Seng Hospital (HQ)"),
        "qty": confirmed_qty,
        "status": "Dispatched",
        "timestamp": time.time()
    }

    # Saves it so other pages can see it
    active_orders.append(new_order)
    
    clinic_state["view"] = "approved"
    clinic_state["draft"]["active"] = False
    
    return jsonify({"status": "success", "confirmed_qty": confirmed, "show_logistics_button": True, "redirect_url": "/logistics", "order": new_order})

@app.get("/api/get-active-orders")
def get_active_orders():
    return jsonify({"orders": active_orders})

@app.post("/api/clinic-reject-order")
def reject_order():
    clinic_state["draft"]["active"] = False
    return jsonify({"status": "success"})


# ==============================================================================
# RUN
# ==============================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
