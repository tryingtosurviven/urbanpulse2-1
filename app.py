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

# --- DEFINE STATE ---
clinic_state = {
    "view": "normal",      
    "protocol": "standard", 
    "draft": {
        "active": False,
        "facility": "---", # NEW FIELD
        "id": "---",
        "qty": 0,
        "cost": "$0"
    }
}

app = Flask(__name__)

# ==============================================================================
# MIDDLEWARE
# ==============================================================================
class WatsonxBypassMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        global clinic_state 
        global AGENT_SYSTEM

        path = environ.get('PATH_INFO', '')
        
        if path == '/api/watsonx-scenario':
            if environ['REQUEST_METHOD'] == 'GET':
                start_response('200 OK', [('Content-Type', 'application/json')])
                return [b'{"status": "bypass_active"}']

            if environ['REQUEST_METHOD'] == 'POST':
                try:
                    try:
                        request_body_size = int(environ.get('CONTENT_LENGTH', 0))
                    except (ValueError):
                        request_body_size = 0
                    
                    request_body = environ['wsgi.input'].read(request_body_size)
                    if not request_body: payload = {}
                    else: payload = json.loads(request_body)
                        
                    raw_key = payload.get("scenario_key", "")
                    scenario_key = raw_key.strip().lower().replace(" ", "_")

                    # --- COMMANDS ---
                    if scenario_key == 'logistics':
                        clinic_state["view"] = 'logistics'
                        start_response('200 OK', [('Content-Type', 'application/json')])
                        return [json.dumps({"status": "success"}).encode('utf-8')]

                    if scenario_key == 'approved':
                        clinic_state["view"] = 'approved'
                        start_response('200 OK', [('Content-Type', 'application/json')])
                        return [json.dumps({"status": "success"}).encode('utf-8')]

                    if scenario_key == 'escalated':
                        clinic_state["protocol"] = "autonomous"
                        start_response('200 OK', [('Content-Type', 'application/json')])
                        return [json.dumps({"status": "success"}).encode('utf-8')]

                    # --- SCENARIO LOGIC ---
                    from scenarios import DEMO_SCENARIOS
                    if AGENT_SYSTEM is None: AGENT_SYSTEM = _build_agent_system()

                    if not scenario_key or scenario_key not in DEMO_SCENARIOS:
                        start_response('400 Bad Request', [('Content-Type', 'application/json')])
                        return [json.dumps({"error": "Invalid key"}).encode('utf-8')]

                    base_scenario = DEMO_SCENARIOS[scenario_key]
                    live_scenario = base_scenario.copy()
                    live_psi = base_scenario["psi_data"].copy()
                    for region in live_psi: live_psi[region] += random.randint(-4, 4) 
                    live_scenario["psi_data"] = live_psi

                    result = AGENT_SYSTEM.run_cycle(live_scenario)
                    
                    risk_data = result.get('risk_assessment', {})
                    psi_val = risk_data.get('current_psi', 'Unknown')
                    risk_level = risk_data.get('risk_level', 'UNKNOWN')
                    supply_data = result.get('supply_chain_actions', {})
                    total_cost = supply_data.get('total_value', '$0')
                    po_id = supply_data.get('po_id', 'No PO')
                    rec_qty = supply_data.get('order_details', {}).get("n95_masks", 500)

                    # --- SAVE DRAFT TO STATE ---
                    clinic_state["draft"] = {
                        "active": True,
                        "facility": "Tan Tock Seng Hospital (HQ)", # <--- HARDCODED FOR DEMO
                        "id": po_id,
                        "qty": rec_qty,
                        "cost": total_cost
                    }
                    
                    if clinic_state["protocol"] == "autonomous":
                        action_text = f"ACTION: ⚡ AUTONOMOUSLY AUTHORIZED {total_cost} (PO: {po_id})."
                    else:
                        action_text = f"RECOMMENDATION: Draft PO {po_id} created for {total_cost}. Waiting for manager approval."

                    ai_summary = (
                        f"🚨 REPORT: {scenario_key.replace('_', ' ').title()}. "
                        f"Risk Level: {risk_level}. Highest PSI: {psi_val}. "
                        f"{action_text}"
                    )
                    
                    response_data = {"status": "success", "scenario": scenario_key, "ai_summary": ai_summary, "raw_data": result}
                    
                    start_response('200 OK', [('Content-Type', 'application/json')])
                    return [json.dumps(response_data).encode('utf-8')]

                except Exception as e:
                    start_response('500 Server Error', [('Content-Type', 'application/json')])
                    return [json.dumps({"error": str(e)}).encode('utf-8')]

        return self.app(environ, start_response)

app.wsgi_app = WatsonxBypassMiddleware(app.wsgi_app)


# -----------------------------
# ROUTES
# -----------------------------
@app.route("/")
def home(): return send_from_directory("static", "index.html")

@app.route("/clinic")
def clinic_dashboard():
    global clinic_state
    clinic_state["view"] = "normal" 
    clinic_state["protocol"] = "standard" 
    clinic_state["draft"]["active"] = False # Reset draft
    return send_from_directory("static", "clinic.html")

@app.get("/api/clinic-poll")
def clinic_poll():
    global AGENT_SYSTEM, clinic_state
    
    if clinic_state["view"] in ['logistics', 'approved']:
         return jsonify({"status": "redirect", "current_view": clinic_state["view"]})

    if AGENT_SYSTEM is None: return jsonify({"status": "waiting"})

    memory = AGENT_SYSTEM.memory
    if not memory: return jsonify({"status": "waiting"})

    last_cycle = memory[-1]
    alert_data = last_cycle.get("healthcare_alerts", {})
    
    return jsonify({
        "status": "alert_active" if alert_data else "waiting",
        "current_view": clinic_state["view"],
        "protocol": clinic_state["protocol"],
        "draft": clinic_state["draft"], 
        "psi": last_cycle.get("risk_assessment", {}).get("current_psi", 0),
        "alert_message": alert_data.get("alert_message", "No message")
    })

@app.post("/api/clinic-confirm-order")
def confirm_order():
    global clinic_state
    data = request.json
    final_qty = data.get("confirmed_qty")
    print(f"✅ CLINIC CONFIRMED ORDER: {final_qty} Masks")
    clinic_state["view"] = "approved"
    clinic_state["draft"]["active"] = False 
    return jsonify({"status": "success", "message": f"Order for {final_qty} masks processed."})

# --- NEW: REJECT ORDER ROUTE ---
@app.post("/api/clinic-reject-order")
def reject_order():
    global clinic_state
    print(f"❌ CLINIC REJECTED ORDER")
    clinic_state["draft"]["active"] = False # Clear draft
    return jsonify({"status": "success", "message": "Order rejected."})

@app.route("/logistics")
def logistics_portal(): return send_from_directory("static", "logistics.html")

@app.route("/citizen")
def citizen_portal(): return send_from_directory("static", "citizen.html")

@app.route("/admin")
def admin_portal(): return send_from_directory("static", "admin.html")

# -----------------------------
# INIT
# -----------------------------
def _build_agent_system():
    from agents import (EnvironmentSentinel, ScalestackAgent, DynamiqMedicalAgent, HealthcarePreparednessAgent, SupplyChainAgent)
    sentinel = EnvironmentSentinel()
    sentinel.register_agent(ScalestackAgent())
    sentinel.register_agent(DynamiqMedicalAgent())
    sentinel.register_agent(HealthcarePreparednessAgent())
    sentinel.register_agent(SupplyChainAgent())
    return sentinel

AGENT_SYSTEM = None

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
