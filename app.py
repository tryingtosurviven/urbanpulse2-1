import os
from flask import Flask, jsonify, Response, request

app = Flask(__name__)

@app.post("/alert")
def alert():
    payload = request.get_json(silent=True) or {}
    # Mock action for demo
    return jsonify({
        "status": "alert_triggered",
        "received": payload
    })

@app.get("/")
def home():
    return {"message": "URBANPULSE is running", "endpoints": ["/health", "/snapshot", "/log", "/alert"]}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/snapshot")
def snapshot():
    from nea_agent import run_snapshot  # lazy import
    return jsonify(run_snapshot())

@app.get("/log")
def log():
    from nea_agent import run_snapshot, format_like_colab  # lazy import
    snap = run_snapshot()
    text = format_like_colab(snap)
    return Response(text, mimetype="text/plain")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
