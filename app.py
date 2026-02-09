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
    "view": "normal",      # Controls: 'normal', 'logistics', 'approved'
    "protocol": "standard" # Controls: 'standard' (Green/Red), 'autonomous' (Purple)
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
                        noise
