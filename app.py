import os
import socket
import time
from flask import Flask, jsonify, Response, request, render_template

# -----------------------------
# Config / flags
# -----------------------------
def is_demo_mode() -> bool:
    # Read DEMO_MODE at request time
    return os.getenv("DEMO_MODE", "false").strip().lower() in ("1", "true", "yes", "y", "on")

INSTANCE = {
    "pid": os.getpid(),
    "host": socket.gethostname(),
    "started_at_epoch": int(time.time()),
    "file": __file__,
}

app = Flask(__name__)

# -----------------------------
# Website routes (Dashboard)
# -----------------------------
@app.get("/")
def dashboard():
    # Requires templates/dashboard.html
    return render_template("dashboard.html")


@app.get("/config")
def config():
    return jsonify({
        "DEMO_MODE": is_demo_mode(),
        "instance": INSTANCE,
        "port_env": os.getenv("PORT", "8080"),
    })


# -----------------------------
# Scenario-based agent APIs
# -----------------------------
def _build_agent_system():
    # Imports are inside so deployment won’t fail if you’re still adding files
    from agents import (
        EnvironmentSentinel,
        ScalestackAgent,
        DynamiqMedicalAgent,
        HealthcarePreparednessAgent,
        SupplyChainAgent
    )

    sentinel = EnvironmentSentinel()
    sentinel.register_agent(ScalestackAgent())
    sentinel.register_agent(DynamiqMedicalAgent())
    sentinel.register_agent(HealthcarePreparednessAgent())
    sentinel.register_agent(SupplyChainAgent())
    return sentinel


# Build once at startup (fast for demo)
AGENT_SYSTEM = None


@app.get("/api/scenarios")
def list_scenarios():
    from scenarios import DEMO_SCENARIOS
    scenarios = [
        {"key": k, "description": v.get("description", ""), "psi_data": v.get("psi_data", {})}
        for k, v in DEMO_SCENARIOS.items()
    ]
    return jsonify({"scenarios": scenarios})


@app.post("/api/run-scenario/<scenario_key>")
def run_scenario(scenario_key: str):
    global AGENT_SYSTEM
    from scenarios import DEMO_SCENARIOS

    if scenario_key not in DEMO_SCENARIOS:
        return jsonify({"error": f"Unknown scenario '{scenario_key}'"}), 404

    if AGENT_SYSTEM is None:
        AGENT_SYSTEM = _build_agent_system()

    result = AGENT_SYSTEM.run_cycle(DEMO_SCENARIOS[scenario_key])
    # Add trace info for demo clarity
    result["_meta"] = {"demo_mode": is_demo_mode(), "instance": INSTANCE}
    return jsonify(result)


# NEW ENDPOINT FOR WATSONX ASSISTANT
@app.post("/api/watsonx-scenario")
def watsonx_scenario():
    global AGENT_SYSTEM
    from scenarios import DEMO_SCENARIOS
    
    # Get key from JSON body instead of URL
    payload = request.get_json(silent=True) or {}
    scenario_key = payload.get("scenario_key")
    
    if not scenario_key or scenario_key not in DEMO_SCENARIOS:
        return jsonify({"error": "Invalid scenario key"}), 400
        
    if AGENT_SYSTEM is None:
        AGENT_SYSTEM = _build_agent_system()
        
    # Execute the simulation
    result = AGENT_SYSTEM.run_cycle(DEMO_SCENARIOS[scenario_key])
    
    # RETURN FORMAT OPTIMIZED FOR AI
    return jsonify({
        "status": "success",
        "scenario": scenario_key,
        "ai_summary": f"Scenario {scenario_key} executed. PSI: {result.get('psi_data', {}).get('value')}. System status: {result.get('decision')}",
        "raw_data": result  # Keep the full data for the dashboard
    })


# -----------------------------
# Existing live-data endpoints
# -----------------------------
@app.get("/health")
def health():
    return jsonify({"status": "ok", "demo_mode": is_demo_mode(), "instance": INSTANCE})


@app.get("/snapshot")
def snapshot():
    # Uses your existing live data fetcher
    from nea_agent import run_snapshot  # lazy import
    data = run_snapshot()
    return jsonify({"demo_mode": is_demo_mode(), "instance": INSTANCE, "data": data})


@app.get("/log")
def log():
    from nea_agent import run_snapshot, format_like_colab  # lazy import
    snap = run_snapshot()
    text = format_like_colab(snap)
    header = (
        f"URBANPULSE LOG\n"
        f"DEMO_MODE={is_demo_mode()}\n"
        f"INSTANCE={INSTANCE}\n"
        f"{'-'*60}\n"
    )
    return Response(header + text, mimetype="text/plain")


@app.post("/alert")
def alert():
    payload = request.get_json(silent=True) or {}

    if is_demo_mode():
        return jsonify({
            "status": "demo_mode_alert_logged",
            "note": "No external systems were triggered",
            "instance": INSTANCE,
            "received": payload
        })

    # Live mode (future: call Xero / MCP tool)
    return jsonify({
        "status": "alert_triggered",
        "instance": INSTANCE,
        "received": payload
    })


# -----------------------------
# Local run
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"[UrbanPulse] Starting on 0.0.0.0:{port} | DEMO_MODE={is_demo_mode()} | FILE={__file__}")
    app.run(host="0.0.0.0", port=port)
