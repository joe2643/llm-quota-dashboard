#!/usr/bin/env python3
"""
LLM Quota Dashboard — Flask Backend
Serves the neumorphic UI + API endpoints.
"""

import json
import subprocess
import os
from pathlib import Path
from flask import Flask, jsonify, send_from_directory, send_file

PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"
SCREENSHOT_DIR = PROJECT_DIR / "output" / "screenshots"
WEB_DIR = Path(__file__).parent

app = Flask(__name__, static_folder=str(WEB_DIR))


@app.route("/")
def index():
    return send_file(WEB_DIR / "index.html")


@app.route("/api/data")
def get_data():
    quota_file = DATA_DIR / "quota_data.json"
    if quota_file.exists():
        return jsonify(json.loads(quota_file.read_text(encoding="utf-8")))
    return jsonify({})


@app.route("/api/providers")
def get_providers():
    providers_file = DATA_DIR / "providers.json"
    if providers_file.exists():
        data = json.loads(providers_file.read_text(encoding="utf-8"))
        return jsonify(data.get("providers", {}))
    return jsonify({})


@app.route("/api/refresh", methods=["POST"])
def refresh():
    try:
        result = subprocess.run(
            ["python3", str(PROJECT_DIR / "scripts" / "check_quota.py"), "--no-cache"],
            capture_output=True, text=True, timeout=180,
            cwd=str(PROJECT_DIR),
        )
        return jsonify({
            "status": "ok" if result.returncode == 0 else "error",
            "output": result.stdout[-500:] if result.stdout else "",
            "error": result.stderr[-300:] if result.stderr else "",
        })
    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "error": "Timeout (180s)"}), 504
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/screenshots/<path:filename>")
def get_screenshot(filename):
    return send_from_directory(str(SCREENSHOT_DIR), filename)


@app.route("/api/screenshots")
def list_screenshots():
    if not SCREENSHOT_DIR.exists():
        return jsonify([])
    files = sorted(SCREENSHOT_DIR.glob("*.png"), key=lambda f: f.stat().st_mtime, reverse=True)
    return jsonify([{"name": f.name, "size": f.stat().st_size} for f in files[:30]])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8501, debug=False)
