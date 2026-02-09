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
    "view": "normal",      # 'normal', 'logistics', 'approved'
    "protocol": "standard", # 'standard', 'autonomous'
    # NEW: Store draft details so frontend can show them
    "draft": {
        "active": False,
        "id": "---",
        "qty": 0,
        "cost": "$0"
    }
}

app = Flask(__name__)

# ==============================================================================
# GOD MODE: WSGI MIDDLEWARE (The Ultimate Bypass)
# ==============================================================================
class WatsonxBypassMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # --- FIX: DECLARE GLOBAL AT THE VERY START ---
        global clinic_state 
        # ---------------------------------------------

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
                    # (Global clinic_state is already declared at top)
                    
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

                    # --- NEW: ESCALATION LOGIC ---
                    if scenario_key == 'escalated':
                        clinic_state["protocol"] = "autonomous" # Flip the switch to Purple
                        print(f"⚡ AGENT COMMAND: Protocol escalated to AUTONOMOUS")
                        
                        status = '200 OK'
                        headers = [('Content-Type', 'application/json')]
                        start_response(status, headers)
                        return [json.dumps({"status": "success", "message": "Protocol escalated"}).encode('utf-8')]
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
                    rec_qty = supply_data.get('order_details', {}).get("n95_masks", 500) # Default to 500

                    # --- NEW: SAVE DRAFT TO STATE ---
                    clinic_state["draft"] = {
                        "active": True,
                        "id": po_id,
                        "qty": rec_qty,
                        "cost": total_cost
                    }
                    
                    # --- FIX: LOGIC FOR DRAFT VS AUTHORIZED ---
                    if clinic_state["protocol"] == "autonomous":
                        action_text = f"ACTION: ⚡ AUTONOMOUSLY AUTHORIZED {total_cost} (PO: {po_id})."
                    else:
                        action_text = f"RECOMMENDATION: Draft PO {po_id} created for {total_cost}. Waiting for manager approval."

                    ai_summary = (
                        f"🚨 REPORT: {scenario_key.replace('_', ' ').title()}. "
                        f"Risk Level: {risk_level}. Highest PSI: {psi_val}. "
                        f"{action_text}"
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
    sentinel.register
