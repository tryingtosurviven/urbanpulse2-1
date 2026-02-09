import os
import socket
import time
import json
import random
from flask import Flask, jsonify, Response, request, send_from_directory

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

# --- DEFINE STATE AT THE TOP SO MIDDLEWARE CAN SEE IT ---
clinic_state = {
    "view": "normal",  # Controls: 'normal', 'logistics', 'approved'
}

app = Flask(__name__)

# ==============================================================================
# GOD MODE: WSGI MIDDLEWARE (The Ultimate Bypass)
# ==============================================================================
class WatsonxBypassMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        
        # 1. TRAP THE SPECIFIC URL
        if path == '/api/watsonx-scenario':
            
            # A. HANDLE BROWSER TEST (GET)
            if environ['REQUEST_METHOD'] == 'GET':
                status = '200 OK'
                headers = [('Content-Type', 'application/json')]
                start_response(status, headers)
                return [b'{"status": "bypass_active", "message": "GOD MODE: Login Wall Destroyed."}']

            # B. HANDLE AI REQUEST (POST)
            if environ['REQUEST_METHOD'] == 'POST':
                try:
                    # Read the JSON body manually
                    try:
                        request_body_size = int(environ.get('CONTENT_LENGTH', 0))
                    except (ValueError):
                        request_body_size = 0
                    
                    request_body = environ['wsgi.input'].read(request_body_size)
                    
                    if not request_body:
                        payload = {}
                    else:
                        payload = json.loads(request_body)
                        
                    raw_key = payload.get("scenario_key", "")
                    scenario_key = raw_key.strip().lower().replace(" ", "_")

                    # ---------------------------------------------------------
                    # [CRITICAL FIX] CHECK FOR CONTROL COMMANDS FIRST
                    # ---------------------------------------------------------
                    global clinic_state
                    
                    if scenario_key == 'logistics':
                        clinic_state["view"] = 'logistics' # Redirect browser
                        print(f"🔄 AGENT COMMAND: Dashboard view switched to LOGISTICS")
                        
                        status = '200 OK'
                        headers = [('Content-Type', 'application/json')]
                        start_response(status, headers)
                        return [json.dumps({"status": "success", "message": "View switched to logistics"}).encode('utf-8')]

                    if scenario_key == 'approved':
                        clinic_state["view"] = 'approved' # Turn sidebar green
                        print(f"✅ AGENT COMMAND: Order APPROVED")
                        
                        status = '200 OK'
                        headers = [('Content-Type', 'application/json')]
                        start_response(status, headers)
                        return [json.dumps({"status": "success", "message": "Order approved"}).encode('utf-8')]
                    # ---------------------------------------------------------

                    # --- RUN SCENARIO LOGIC (Existing Haze Logic) ---
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

                    # GET THE BASE SCENARIO & ADD NOISE
                    base_scenario = DEMO_SCENARIOS[scenario_key]
                    live_scenario = base_scenario.copy()
                    live_psi = base_scenario["psi_data"].copy()
                    
                    for region in live_psi:
                        noise = random.randint(-4, 4) 
                        live_psi[region] += noise
                    
                    live_scenario["psi_data"] = live_psi

                    # Run Simulation
                    result = AGENT_SYSTEM.run_cycle(live_scenario)
                    
                    # Generate Summary
                    risk_data = result.get('risk_assessment', {})
                    psi_val = risk_data.get('current_psi', 'Unknown')
                    risk_level = risk_data.get('risk_level', 'UNKNOWN')
                    supply_data = result.get('supply_chain_actions', {})
                    total_cost = supply_data.get('total_value', '$0')
                    po_id = supply_data.get('po_id', 'No PO')
                    
                    ai_summary = (
                        f"🚨 REPORT: {scenario_key.replace('_', ' ').title()}. "
                        f"Risk Level: {risk_level}. Highest PSI: {psi_val}. "
                        f"ACTION: Authorized {total_cost} for supplies (PO: {po_id})."
                    )
                    
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

        # 2. IF NOT OUR URL, LET FLASK HANDLE IT
        return self.app(environ, start_response)

# Apply the middleware
app.wsgi_app = WatsonxBypassMiddleware(app.wsgi_app)


# -----------------------------
# Website routes (Dashboard)
# -----------------------------
@app.get("/")
def home():
    return send_from_directory("static", "index.html")

@app.get("/config")
def config():
    return jsonify({"DEMO_MODE": is_demo_mode(), "instance": INSTANCE})

# -----------------------------
# Agent System Builder
# -----------------------------
def _build_agent_system():
    from agents import (
        EnvironmentSentinel, ScalestackAgent, DynamiqMedicalAgent,
        HealthcarePreparednessAgent, SupplyChainAgent
    )
    sentinel = EnvironmentSentinel()
    sentinel.register_agent(ScalestackAgent())
    sentinel.register_agent(DynamiqMedicalAgent())
    sentinel.register_agent(HealthcarePreparednessAgent())
    sentinel.register_agent(SupplyChainAgent())
    return sentinel

AGENT_SYSTEM = None

@app.get("/api/scenarios")
def list_scenarios():
    from scenarios import DEMO_SCENARIOS
    scenarios = [
        {"key": k, "description": v.get("description", ""), "psi_data": v.get("psi_data", {})}
        for k, v in DEMO_SCENARIOS.items()
    ]
    return jsonify({"scenarios": scenarios})

# -----------------------------
# CLINIC DEMO ROUTES
# -----------------------------
@app.route("/clinic")
def clinic_dashboard():
    global clinic_state
    clinic_state["view"] = "normal"  # Force system back to "Normal"
    return send_from_directory("static", "clinic.html")

@app.get("/api/clinic-poll")
def clinic_poll():
    global AGENT_SYSTEM, clinic_state
    
    # 1. Check for State Redirects (Logistics / Approved)
    if clinic_state["view"] in ['logistics', 'approved']:
         return jsonify({"status": "redirect", "current_view": clinic_state["view"]})

    # 2. Check for Agent Alerts
    if AGENT_SYSTEM is None:
        return jsonify({"status": "waiting", "current_view": "normal"})

    memory = AGENT_SYSTEM.memory
    if not memory:
        return jsonify({"status": "waiting", "current_view": "normal"})

    last_cycle = memory[-1]
    alert_data = last_cycle.get("healthcare_alerts", {})
    supply_data = last_cycle.get("supply_chain_actions", {})
    
    return jsonify({
        "status": "alert_active" if alert_data else "waiting",
        "current_view": clinic_state["view"],
        "psi": last_cycle.get("risk_assessment", {}).get("current_psi", 0),
        "risk_level": last_cycle.get("risk_assessment", {}).get("risk_level", "UNKNOWN"),
        "recommended_masks": supply_data.get("order_details", {}).get("n95_masks", 0),
        "alert_message": alert_data.get("alert_message", "No message")
    })

@app.post("/api/clinic-confirm-order")
def confirm_order():
    data = request.json
    final_qty = data.get("confirmed_qty")
    print(f"✅ CLINIC CONFIRMED ORDER: {final_qty} Masks")
    return jsonify({"status": "success", "message": f"Order for {final_qty} masks processed."})

@app.route("/logistics")
def logistics_portal():
    return send_from_directory("static", "logistics.html")

@app.route("/citizen")
def citizen_portal():
    return send_from_directory("static", "citizen.html")

@app.route("/admin")
def admin_portal():
    return send_from_directory("static", "admin.html")

# -----------------------------
# Local run
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"[UrbanPulse] Starting on 0.0.0.0:{port} | DEMO_MODE={is_demo_mode()}")
    app.run(host="0.0.0.0", port=port)
