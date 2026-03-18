import os
import socket
import time
import json
import random
import datetime
import anthropic

from typing import Any, Dict, Optional

from flask import Flask, jsonify, request, send_from_directory
#from ibm_watsonx_ai.foundation_models import Model
#from ibm_watsonx_ai import Credentials
from dotenv import load_dotenv

load_dotenv()  # Loads variables from .env into environment

# INPUT VALIDATION — whitelisted scenario keys
VALID_SCENARIOS = {
    "low_haze",
    "moderate_haze",
    "severe_haze",
    "dengue_low",
    "dengue_medium",
    "dengue_high",
}

def write_governance_log(entry: Dict[str, Any]):
    """
    Writes a permanent audit trail of AI decisions to a local file.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = (
        f"[{timestamp}] "
        f"PO: {entry.get('id')} | "
        f"PSI: {entry.get('psi', 'N/A')} | "
        f"Dengue Cases: {entry.get('projected_cases', 'N/A')} | "
        f"{entry.get('governance_log', '')}\n"
    )

    with open("governance.log", "a", encoding="utf-8") as f:
        f.write(log_line)


# ==============================================================================
# CONFIG
# ==============================================================================
def env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "y", "on")


def is_demo_mode() -> bool:
    # Demo mode means: allow fallback if watsonx fails
    return env_bool("DEMO_MODE", "true")


def watsonx_enabled() -> bool:
    # Live watsonx means we have the required creds set AND WATSONX_ENABLED true
    return env_bool("WATSONX_ENABLED", "true") and all(
        os.getenv(k)
        for k in ("WATSONX_API_KEY", "WATSONX_URL", "WATSONX_PROJECT_ID", "WATSONX_MODEL_ID")
    )


INSTANCE = {
    "pid": os.getpid(),
    "host": socket.gethostname(),
    "started_at_epoch": int(time.time()),
    "file": __file__,
}

APP_VERSION = "urbanpulse-r3-haze-dengue-1.0"

app = Flask(__name__)

from auth import require_role, login_endpoint  # noqa: E402

app.register_blueprint(login_endpoint)

# ==============================================================================
# GLOBAL STATE
# ==============================================================================
clinic_state = {
    "view": "normal",
    "protocol": "standard",
    "draft": {
        "active": False,
        "facility": "---",
        "id": "---",
        "qty": 0,
        "cost": "$0",
        "reason": "",
        "autonomous": False,
        "psi": None,
        "projected_cases": None,
        "risk_level": "LOW",
        "governance_log": "",
    },
}

AGENT_SYSTEM = None
WATSONX_MODEL = None


# ==============================================================================
# HELPERS
# ==============================================================================
def _is_dengue_scenario(scenario_key: str) -> bool:
    return scenario_key.startswith("dengue_")


def _is_haze_scenario(scenario_key: str) -> bool:
    return not _is_dengue_scenario(scenario_key)


def _risk_from_psi(highest_psi: int) -> str:
    if highest_psi >= 200:
        return "SEVERE"
    if highest_psi >= 101:
        return "MODERATE"
    return "LOW"


def _risk_from_dengue(highest_cases: int) -> str:
    if highest_cases >= 20:
        return "HIGH"
    if highest_cases >= 10:
        return "MEDIUM"
    return "LOW"


def _build_agent_system():
    """
    Local multi-agent fallback for haze mode.
    """
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
#def _get_watsonx_model() -> Optional[Model]:
#    """
#    Returns a cached watsonx Model if credentials exist, else None.
#    """
#    global WATSONX_MODEL
#    if WATSONX_MODEL is not None:
#        return WATSONX_MODEL

#    if not watsonx_enabled():
#        return None

#    creds = Credentials(
#        url=os.getenv("WATSONX_URL"),
#        api_key=os.getenv("WATSONX_API_KEY"),
#    )

#    WATSONX_MODEL = Model(
#        model_id=os.getenv("WATSONX_MODEL_ID"),
#        credentials=creds,
#        project_id=os.getenv("WATSONX_PROJECT_ID"),
#    )
#    return WATSONX_MODEL


def _claude_reason(prompt: str) -> Dict[str, Any]:
    """
    Calls Claude API as AI reasoning engine.
    Drop-in replacement for _watsonx_reason.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",  # Fast + cheap for demo
        max_tokens=450,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    text_out = message.content[0].text
    
    # Extract JSON from response
    start = text_out.find("{")
    end = text_out.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Claude did not return JSON. Raw: {text_out[:300]}")
    
    return json.loads(text_out[start:end + 1])

def claude_enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))

# SCENARIO / PROMPTS
def _scenario_with_jitter(base: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(base)

    if "psi_data" in base and isinstance(base["psi_data"], dict):
        updated["psi_data"] = {
            region: max(0, int(val) + random.randint(-3, 3))
            for region, val in base["psi_data"].items()
        }

    if "dengue_data" in base and isinstance(base["dengue_data"], dict):
        updated["dengue_data"] = {
            region: max(0, int(val) + random.randint(-2, 2))
            for region, val in base["dengue_data"].items()
        }
        updated["projected_cases"] = max(updated["dengue_data"].values()) if updated["dengue_data"] else 0

    return updated


def _policy_autonomous_only_for_severe(scenario_key: str, risk_level: str, highest_value: int) -> bool:
    """
    ONLY severe haze can fully auto-dispatch.
    Dengue stays human-in-loop.
    """
    return scenario_key == "severe_haze"


def _build_haze_watsonx_prompt(scenario_key: str, psi_data: Dict[str, int]) -> str:
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
  "recommended_qty": <int>,
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
- Suggested qty guidance:
  - LOW: 200–400
  - MODERATE: 500–900
  - SEVERE: 1000–1600
- Choose affected_regions where PSI >= (highest_psi - 10).
- governance.auto_dispatch_allowed must be true ONLY if scenario_key == "severe_haze".
""".strip()


def _build_dengue_watsonx_prompt(scenario_key: str, dengue_data: Dict[str, int]) -> str:
    return f"""
You are "UrbanPulse PublicHealthSentinel", supporting Singapore dengue monitoring.

Context:
- Urban problem: dengue cluster activity increases mosquito-borne infection risk.
- Objective: classify district risk, estimate response stock quantity, and generate a citizen advisory.
- Safety policy: Dengue scenarios remain human-in-loop and do NOT auto-dispatch.

Inputs:
scenario_key: "{scenario_key}"
Projected dengue cases by district:
{json.dumps(dengue_data, indent=2)}

Output:
Return STRICT JSON only with these keys:
{{
  "risk_level": "LOW|MEDIUM|HIGH",
  "highest_cases": <int>,
  "affected_regions": [<district strings>],
  "recommended_qty": <int>,
  "justification": "<1-3 sentences>",
  "citizen_advice": "<1-2 sentences>",
  "clinic_action": "<1-2 sentences>",
  "data_sources": ["NEA / MOH-style demo scenarios", "Vector surveillance signals (simulated)"],
  "governance": {{
    "human_in_loop": true,
    "auto_dispatch_allowed": false,
    "why": "Dengue scenarios require manual review."
  }}
}}

Rules:
- Use the highest projected district case count as the main driver.
- Risk guidance:
  - LOW if highest_cases < 10
  - MEDIUM if highest_cases 10-19
  - HIGH if highest_cases >= 20
- Choose affected_regions where cases >= (highest_cases - 3).
- recommended_qty is a generic preparedness stock estimate for repellent / prevention packs.
""".strip()


# ==============================================================================
# CORE: SCENARIO EXECUTION
# ==============================================================================
def run_scenario_with_watsonx_first(scenario_key: str) -> Dict[str, Any]:
    """
    Main function:
    - Haze: tries live watsonx first, then local MAS fallback.
    - Dengue: tries live watsonx first, then deterministic local fallback.
    """
    global AGENT_SYSTEM, clinic_state

    from scenarios import DEMO_SCENARIOS

    if scenario_key not in DEMO_SCENARIOS:
        raise ValueError(f"Invalid scenario: {scenario_key}")

    base = DEMO_SCENARIOS[scenario_key]
    scenario = _scenario_with_jitter(base)

    is_dengue = _is_dengue_scenario(scenario_key)
    agent_logs = []
    used_watsonx = False
    watsonx_error = None
    decision: Optional[Dict[str, Any]] = None

    # --------------------------------------------------------------------------
    # 1) Live watsonx (preferred)
    # --------------------------------------------------------------------------
    if claude_enabled():
        try:
            if is_dengue:
                agent_logs.append({
                    "agent": "PublicHealthSentinel",
                    "action": "Calling Claude AI dengue reasoning",
                    "ts": time.time(),
                })
                decision = _claude_reason(
                    _build_dengue_watsonx_prompt(scenario_key, scenario["dengue_data"])
                )
            else:
                agent_logs.append({
                    "agent": "EnvironmentSentinel",
                    "action": "Calling Claude AI haze reasoning",
                    "ts": time.time(),
                })
                decision = _claude_reason(
                    _build_haze_watsonx_prompt(scenario_key, scenario["psi_data"])
                )

            used_watsonx = True
            agent_logs.append({
                "agent": "ClaudeAI",
                "action": "Decision returned",
                "ts": time.time(),
            })
        except Exception as e:
            watsonx_error = str(e)
            agent_logs.append({
                "agent": "ClaudeAI",
                "action": "Claude failed, fallback engaged",
                "error": watsonx_error,
                "ts": time.time(),
            })
            if not is_demo_mode():
                raise

    # --------------------------------------------------------------------------
    # 2) Fallback logic
    # --------------------------------------------------------------------------
    if decision is None:
        if is_dengue:
            dengue_data = scenario["dengue_data"]
            highest_cases = max(dengue_data.values()) if dengue_data else 0
            risk_level = _risk_from_dengue(highest_cases)
            affected_regions = [
                region for region, val in dengue_data.items() if val >= max(0, highest_cases - 3)
            ]

            if risk_level == "HIGH":
                recommended_qty = 850
            elif risk_level == "MEDIUM":
                recommended_qty = 450
            else:
                recommended_qty = 180

            decision = {
                "risk_level": risk_level,
                "highest_cases": highest_cases,
                "affected_regions": affected_regions,
                "recommended_qty": recommended_qty,
                "justification": "Vector risk signals processed and fallback dengue thresholds applied.",
                "citizen_advice": (
                    "Remove stagnant water, use repellent, and monitor for fever or body aches."
                ),
                "clinic_action": (
                    "Prepare dengue advisory messaging and preventive response supplies."
                ),
                "data_sources": [
                    "NEA / MOH-style demo scenarios",
                    "Vector surveillance signals (simulated)",
                ],
                "governance": {
                    "human_in_loop": True,
                    "auto_dispatch_allowed": False,
                    "why": "Dengue scenarios require manual review.",
                },
            }

            agent_logs.extend([
                {
                    "agent": "PublicHealthSentinel",
                    "action": "Vector risk signals processed",
                    "ts": time.time(),
                },
                {
                    "agent": "ClusterMonitor",
                    "action": "Cluster escalation threshold evaluated",
                    "ts": time.time(),
                },
                {
                    "agent": "CitizenAdvisoryAgent",
                    "action": "Citizen advisory generated",
                    "ts": time.time(),
                },
            ])
        else:
            if AGENT_SYSTEM is None:
                AGENT_SYSTEM = _build_agent_system()

            agent_logs.append({
                "agent": "EnvironmentSentinel",
                "action": "Running local multi-agent cycle (fallback)",
                "ts": time.time(),
            })
            result = AGENT_SYSTEM.run_cycle(scenario)

            risk = result.get("risk_assessment", {})
            supply = result.get("supply_chain_actions", {})
            psi_by_region = scenario["psi_data"]

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
                "affected_regions": [region for region, val in psi_by_region.items() if val >= highest - 10],
                "recommended_qty": int(rec_qty),
                "justification": "Fallback MAS computed risk and recommended stock buffer.",
                "citizen_advice": "Limit outdoor activity if PSI is elevated; wear a mask if needed.",
                "clinic_action": "Prepare respiratory supplies; review N95 stock levels.",
                "data_sources": [
                    "NEA PSI feed (simulated for demo)",
                    "MOH haze guidance (conceptual)",
                ],
                "governance": {
                    "human_in_loop": scenario_key != "severe_haze",
                    "auto_dispatch_allowed": scenario_key == "severe_haze",
                    "why": "Auto-dispatch restricted to severe haze only.",
                },
            }

    # --------------------------------------------------------------------------
    # 3) Normalize decision
    # --------------------------------------------------------------------------
    if is_dengue:
        dengue_data = scenario["dengue_data"]
        highest_value = int(decision.get("highest_cases", max(dengue_data.values())))
        risk_level = str(decision.get("risk_level", _risk_from_dengue(highest_value))).upper()
        recommended_qty = int(decision.get("recommended_qty", 200))
        affected_regions = decision.get("affected_regions") or list(dengue_data.keys())
        primary_metric_name = "projected_cases"
        primary_metric_value = highest_value
    else:
        psi_by_region = scenario["psi_data"]
        highest_value = int(decision.get("highest_psi", max(psi_by_region.values())))
        risk_level = str(decision.get("risk_level", _risk_from_psi(highest_value))).upper()
        recommended_qty = int(decision.get("recommended_qty", 500))
        affected_regions = decision.get("affected_regions") or list(psi_by_region.keys())
        primary_metric_name = "psi"
        primary_metric_value = highest_value

    # Governance policy
    autonomous = _policy_autonomous_only_for_severe(scenario_key, risk_level, highest_value)
    clinic_state["protocol"] = "autonomous" if autonomous else "standard"

    # --------------------------------------------------------------------------
    # 4) Operational safety
    # --------------------------------------------------------------------------
    prediction_value = recommended_qty

    if prediction_value > 500 and not autonomous:
        status_msg = "⚠️ PENDING APPROVAL (High Surge Predicted)"
        governance_note = "AI predicted a surge > 500. Manual verification required per Protocol 4.2."
    elif autonomous:
        status_msg = "⚡ AUTO-DISPATCHED (Severe Haze Protocol)"
        governance_note = "PSI >= 200. Autonomous dispatch authorised under Protocol 3.1."
    else:
        status_msg = "✅ Monitoring (Normal Levels)"
        governance_note = "Prediction within normal operating parameters."

    clinic_state["protocol"] = "autonomous" if autonomous else "standard"

    po_id = f"PO-{int(time.time())}"

    clinic_state["draft"] = {
        "active": True,
        "facility": "Tan Tock Seng Hospital (HQ)",
        "id": po_id,
        "qty": recommended_qty,
        "cost": "$—",
        "reason": f"{status_msg} | {decision.get('justification', '')}",
        "autonomous": autonomous,
        "psi": highest_value if not is_dengue else None,
        "projected_cases": highest_value if is_dengue else None,
        "risk_level": risk_level,
        "governance_log": governance_note,
    }

    write_governance_log(clinic_state["draft"])

    if is_dengue:
        agent_logs.extend([
            {
                "agent": "PublicHealthSentinel",
                "action": f"Highest projected cases={highest_value} → risk={risk_level}",
                "ts": time.time(),
            },
            {
                "agent": "PreparednessAgent",
                "action": f"Recommended preparedness stock qty={recommended_qty}",
                "ts": time.time(),
            },
            {
                "agent": "Governance",
                "action": "Human approval required",
                "ts": time.time(),
            },
        ])
    else:
        agent_logs.extend([
            {
                "agent": "EnvironmentSentinel",
                "action": f"PSI highest={highest_value} → risk={risk_level}",
                "ts": time.time(),
            },
            {
                "agent": "SupplyChainAgent",
                "action": f"Recommended N95 order qty={recommended_qty}",
                "ts": time.time(),
            },
            {
                "agent": "Governance",
                "action": "Auto-dispatch ONLY on severe_haze" if autonomous else "Human approval required",
                "ts": time.time(),
            },
        ])

    # --------------------------------------------------------------------------
    # 5) Response
    # --------------------------------------------------------------------------
    if is_dengue:
        raw_data = {
            "dengue_data": scenario["dengue_data"],
            "projected_cases": highest_value,
        }
        risk_assessment = {
            "risk_level": risk_level,
            "affected_regions": affected_regions,
            "projected_cases": highest_value,
        }
        alert_message = decision.get("clinic_action", "")
        citizen_advice = decision.get("citizen_advice", "")
    else:
        raw_data = {
            "psi_data": scenario["psi_data"],
        }
        risk_assessment = {
            "current_psi": highest_value,
            "risk_level": risk_level,
            "affected_regions": affected_regions,
        }
        alert_message = decision.get("clinic_action", "")
        citizen_advice = decision.get("citizen_advice", "")

    return {
        "status": "success",
        "scenario": scenario_key,
        "mode": "dengue" if is_dengue else "haze",
        "watsonx": {
            "enabled": watsonx_enabled(),
            "used": used_watsonx,
            "error": watsonx_error,
            "model_id": os.getenv("WATSONX_MODEL_ID", ""),
            "project_id": os.getenv("WATSONX_PROJECT_ID", ""),
        },
        "raw_data": raw_data,
        "risk_assessment": risk_assessment,
        "healthcare_alerts": {
            "alert_message": alert_message,
            "citizen_advice": citizen_advice,
        },
        "supply_chain_actions": {
            "recommended_qty": recommended_qty,
            "po_id": po_id,
            "autonomous": autonomous,
            "justification": decision.get("justification", ""),
            "governance": decision.get("governance", {}),
        },
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
@require_role("clinic_manager", "admin")
def clinic_portal():
    clinic_state["view"] = "normal"
    clinic_state["protocol"] = "standard"
    clinic_state["draft"]["active"] = False
    return send_from_directory("static", "clinic.html")


@app.route("/logistics")
@require_role("clinic_manager", "admin")
def logistics_portal():
    return send_from_directory("static", "logistics.html")


@app.route("/admin")
@require_role("admin")
def admin_portal():
    return send_from_directory("static", "admin.html")


@app.route("/api/scenario/<scenario_key>")
def get_scenario(scenario_key):
    from scenarios import DEMO_SCENARIOS

    if scenario_key not in DEMO_SCENARIOS:
        return jsonify({"error": "Scenario not found"}), 404

    base_scenario = DEMO_SCENARIOS[scenario_key]
    live_scenario = _scenario_with_jitter(base_scenario)

    return jsonify(live_scenario)


# Public endpoint for citizen map
@app.post("/api/public/run-scenario/<scenario_key>")
def api_public_run_scenario(scenario_key):
    key = scenario_key.strip().lower()
    if key not in VALID_SCENARIOS:
        return jsonify({"error": "Invalid scenario", "code": "INVALID_SCENARIO_KEY"}), 400
    try:
        result = run_scenario_with_watsonx_first(key)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "instance": INSTANCE}), 400



@app.post("/api/run-scenario/<scenario_key>")
@require_role("admin")
def api_run_scenario(scenario_key):
    key = scenario_key.strip().lower()
    if key not in VALID_SCENARIOS:
        return jsonify({"error": "Invalid scenario", "code": "INVALID_SCENARIO_KEY"}), 400
    try:
        result = run_scenario_with_watsonx_first(key)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "instance": INSTANCE}), 400


@app.post("/api/watsonx-scenario")
@require_role("admin")
def watsonx_scenario():
    payload = request.json or {}
    raw_key = payload.get("scenario_key", "")
    scenario_key = raw_key.strip().lower().replace(" ", "_")
    
    # ADD THIS:
    if scenario_key not in VALID_SCENARIOS:
        return jsonify({"error": "Invalid scenario", "code": "INVALID_SCENARIO_KEY"}), 400
    
    try:
        result = run_scenario_with_watsonx_first(scenario_key)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "instance": INSTANCE}), 400


# ==============================================================================
# API: CLINIC POLLING / ORDERS
# ==============================================================================
@app.get("/api/clinic-poll")
@require_role("clinic_manager", "admin")
def clinic_poll():
    if not clinic_state["draft"].get("active"):
        return jsonify({
            "status": "waiting",
            "current_view": clinic_state["view"],
            "protocol": clinic_state["protocol"],
        })

    return jsonify({
        "status": "alert_active",
        "current_view": clinic_state["view"],
        "protocol": clinic_state["protocol"],
        "draft": clinic_state["draft"],
        "psi": clinic_state["draft"].get("psi", 0) or 0,
        "projected_cases": clinic_state["draft"].get("projected_cases", 0) or 0,
        "alert_message": clinic_state["draft"].get("reason", ""),
    })


@app.post("/api/clinic-confirm-order")
@require_role("clinic_manager", "admin")
def confirm_order():
    data = request.json or {}
    confirmed = int(data.get("confirmed_qty") or 0)

    user = getattr(request, "current_user", {})
    print(
        f"[AUDIT] Order confirmed: qty={confirmed} "
        f"by={user.get('username', 'unknown')} "
        f"role={user.get('role', 'unknown')}"
    )

    clinic_state["view"] = "approved"
    clinic_state["draft"]["active"] = False
    return jsonify({
        "status": "success",
        "confirmed_qty": confirmed,
        "confirmed_by": user.get("username"),
    })


@app.post("/api/clinic-reject-order")
@require_role("clinic_manager", "admin")
def reject_order():
    user = getattr(request, "current_user", {})
    print(f"[AUDIT] Order rejected by={user.get('username', 'unknown')}")
    clinic_state["draft"]["active"] = False
    return jsonify({"status": "success"})

@app.get("/api/lta-eta/<facility_id>")
@require_role("clinic_manager", "admin")
def lta_eta(facility_id):
    """
    Returns live delivery ETA from central warehouse to facility.
    Uses LTA DataMall TrafficSpeedBands API.
    Called by logistics.html after a PO is dispatched.
    """
    try:
        from lta_agent import get_delivery_eta
        eta_data = get_delivery_eta(facility_id.strip().lower())
        return jsonify({"status": "success", **eta_data})
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "display": "⏱ ETA unavailable",
        }), 500

@app.route("/access-denied")
def access_denied():
    return send_from_directory("static", "access_denied.html"), 403


@app.route("/login")
def login_page():
    return send_from_directory("static", "login.html")


# ==============================================================================
# RUN
# ==============================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)