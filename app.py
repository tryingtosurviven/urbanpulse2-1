import os
import socket
import time
import json
from flask import Flask, jsonify, Response, request, render_template, send_from_directory

# -----------------------------
# Config / flags
# -----------------------------
def is_demo_mode() -> bool:
    return os.getenv("DEMO_MODE", "false").strip().lower() in ("1", "true", "yes", "y", "on")

INSTANCE = {
    "pid": os.getpid(),
    "host": socket.gethostname(),
    "started_at_epoch": int(time.time()),
    "file": __file__,
}

app = Flask(__name__)

# ==============================================================================
# GOD MODE: WSGI MIDDLEWARE (The Ultimate Bypass)
# This sits ABOVE Flask. It intercepts the request before any login checks occur.
# ==============================================================================
class WatsonxBypassMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        
        # 1. TRAP THE SPECIFIC URL
        if path == '/api/watsonx-scenario':
            
            # A. HANDLE BROWSER TEST (GET) - Proves the tunnel is open
            if environ['REQUEST_METHOD'] == 'GET':
                status = '200 OK'
                headers = [('Content-Type', 'application/json')]
                start_response(status, headers)
                return [b'{"status": "bypass_active", "message": "GOD MODE: Login Wall Destroyed. The tunnel is open."}']

            # B. HANDLE AI REQUEST (POST) - Runs the logic manually
            if environ['REQUEST_METHOD'] == 'POST':
                try:
                    # Read the JSON body manually
                    try:
                        request_body_size = int(environ.get('CONTENT_LENGTH', 0))
                    except (ValueError):
                        request_body_size = 0
                    
                    request_body = environ['wsgi.input'].read(request_body_size)
                    
                    # Parse JSON
                    if not request_body:
                        payload = {}
                    else:
                        payload = json.loads(request_body)
                        
                    raw_key = payload.get("scenario_key", "")
                    scenario_key = raw_key.strip().lower().replace(" ", "_")

                    # --- RUN LOGIC MANUALLY (No Flask Request Context needed) ---
                    # We import here to ensure we have access to the latest data
                    from scenarios import DEMO_SCENARIOS
                    global AGENT_SYSTEM
                    
                    if AGENT_SYSTEM is None:
                        AGENT_SYSTEM = _build_agent_system()

                    # Check key
                    if not scenario_key or scenario_key not in DEMO_SCENARIOS:
                        status = '400 Bad Request'
                        headers = [('Content-Type', 'application/json')]
                        start_response(status, headers)
                        return [json.dumps({"status": "error", "message": f"Invalid key: {raw_key}"}).encode('utf-8')]

                    # Run Simulation
                    result = AGENT_SYSTEM.run_cycle(DEMO_SCENARIOS[scenario_key])
                    
                    # Format Response
                    ai_summary = f"Simulation triggered for {raw_key}! PSI: {result.get('psi_data', {}).get('value')}. Status: {result.get('decision')}. Coordination summary: {result.get('summary', 'No report.')}"
                    
                    response_data = {
                        "status": "success",
                        "scenario": scenario_key,
                        "ai_summary": ai_summary,
                        "raw_data": result
                    }
                    
                    status = '200 OK'
                    headers = [('Content-Type', 'application/json')]
                    start_response(status, headers)
                    return [json.dumps(response_data).encode('utf-8')]

                except Exception as e:
                    status = '500 Server Error'
                    headers = [('Content-Type', 'application/json')]
                    start_response(status, headers)
                    return [json.dumps({"status": "error", "message": str(e)}).encode('utf-8')]

        # 2. IF NOT OUR URL, LET FLASK HANDLE IT (Login page, etc.)
        return self.app(environ, start_response)

# Apply the middleware to the app
app.wsgi_app = WatsonxBypassMiddleware(app.wsgi_app)
# ==============================================================================


# -----------------------------
# Website routes (Dashboard)
# -----------------------------
@app.get("/")
def home():
    return send_from_directory("static", "index.html")

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

# Build once at startup
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
    result["_meta"] = {"demo_mode": is_demo_mode(), "instance": INSTANCE}
    return jsonify(result)

# -----------------------------
# Existing live-data endpoints
# -----------------------------
@app.get("/health")
def health():
    return jsonify({"status": "ok", "demo_mode": is_demo_mode(), "instance": INSTANCE})

@app.get("/snapshot")
def snapshot():
    from nea_agent import run_snapshot
    data = run_snapshot()
    return jsonify({"demo_mode": is_demo_mode(), "instance": INSTANCE, "data": data})

@app.get("/log")
def log():
    from nea_agent import run_snapshot, format_like_colab
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
