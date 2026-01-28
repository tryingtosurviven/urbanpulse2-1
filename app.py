import os
from flask import Flask, jsonify, Response
from nea_agent import run_snapshot, format_like_colab

app = Flask(__name__)

@app.get("/")
def home():
    return {"message": "URBANPULSE is running", "endpoints": ["/health", "/snapshot", "/log"]}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/snapshot")
def snapshot():
    return jsonify(run_snapshot())

@app.get("/log")
def log():
    snap = run_snapshot()
    text = format_like_colab(snap)
    return Response(text, mimetype="text/plain")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
