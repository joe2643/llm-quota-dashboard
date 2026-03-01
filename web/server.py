#!/usr/bin/env python3
"""
LLM Quota Dashboard — Flask Backend
Serves the neumorphic UI + API endpoints.
Auto-refreshes data via background scraper thread.
"""

import json
import subprocess
import os
import threading
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
import sys
sys.path.insert(0, os.path.dirname(__file__))
from history import record_snapshot, get_history, cleanup
from flask import Flask, jsonify, send_from_directory, send_file, request, Response
import queue

PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"
SCREENSHOT_DIR = PROJECT_DIR / "output" / "screenshots"
WEB_DIR = Path(__file__).parent
SCRAPER_SCRIPT = PROJECT_DIR / "scripts" / "scrape_dashboards_parallel.py"
QUOTA_FILE = DATA_DIR / "quota_data.json"

CDP_PORT = 18800
REFRESH_INTERVAL = 30 * 60   # 30 minutes
STALE_THRESHOLD = 45 * 60    # consider data stale after 45min

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("dashboard")

app = Flask(__name__, static_folder=str(WEB_DIR))

# ─── SSE (Server-Sent Events) ───────────────────────────────────

_sse_clients = []  # list of queue.Queue
_sse_lock = threading.Lock()


def _sse_broadcast(event_type, data):
    """Send event to all connected SSE clients."""
    msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    with _sse_lock:
        dead = []
        for q in _sse_clients:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)

# ─── Background scraper ─────────────────────────────────────────

_scraper_lock = threading.Lock()
_last_scrape_ok = 0


_chrome_process = None

def _ensure_chrome():
    """Start headless Chrome with CDP if not already running."""
    global _chrome_process
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=3)
        return True  # already running
    except:
        pass

    # Try to start headless Chrome
    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ]
    chrome_bin = None
    for p in chrome_paths:
        if os.path.exists(p):
            chrome_bin = p
            break
    if not chrome_bin:
        log.warning("Chrome not found, cannot start CDP")
        return False

    # Copy Chrome profile for session reuse in headless mode
    chrome_profile = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    headless_profile = Path("/tmp/chrome-cdp-dashboard")
    if chrome_profile.exists() and not (headless_profile / "Default" / "Cookies").exists():
        log.info("Copying Chrome profile for headless session reuse...")
        (headless_profile / "Default").mkdir(parents=True, exist_ok=True)
        for f in ["Cookies", "Login Data", "Preferences"]:
            src = chrome_profile / "Default" / f
            if src.exists():
                import shutil
                shutil.copy2(str(src), str(headless_profile / "Default" / f))
        for d in ["Local Storage", "Session Storage"]:
            src = chrome_profile / "Default" / d
            if src.exists():
                import shutil
                dst = headless_profile / "Default" / d
                if not dst.exists():
                    shutil.copytree(str(src), str(dst))
        ls_src = chrome_profile / "Local State"
        if ls_src.exists():
            import shutil
            shutil.copy2(str(ls_src), str(headless_profile / "Local State"))

    log.info(f"Starting headless Chrome on port {CDP_PORT}...")
    _chrome_process = subprocess.Popen(
        [chrome_bin, f"--remote-debugging-port={CDP_PORT}",
         "--headless=new", "--disable-gpu", "--no-first-run",
         f"--user-data-dir={headless_profile}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    # Wait for CDP to be ready
    for _ in range(20):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2)
            log.info("Headless Chrome started")
            return True
        except:
            pass
    log.warning("Chrome started but CDP not responding")
    return False


def _run_scraper():
    """Run the CDP scraper, return True on success."""
    global _last_scrape_ok
    if not _scraper_lock.acquire(blocking=False):
        log.info("Scraper already running, skipping")
        return False
    try:
        if not _ensure_chrome():
            log.warning("No Chrome available, skipping scrape")
            return False
        log.info("Running scraper...")
        result = subprocess.run(
            ["python3", str(SCRAPER_SCRIPT)],
            capture_output=True, text=True, timeout=300,
            cwd=str(PROJECT_DIR),
        )
        if result.returncode == 0:
            _last_scrape_ok = time.time()
            log.info("Scraper OK")
            # Record snapshot to history + broadcast SSE
            try:
                if QUOTA_FILE.exists():
                    qdata = json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
                    n = record_snapshot(qdata)
                    log.info(f"Recorded {n} history points")
                    _sse_broadcast("refresh", qdata)
            except Exception as e:
                log.warning(f"History record failed: {e}")
            return True
        else:
            log.warning(f"Scraper failed (rc={result.returncode}): {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        log.warning("Scraper timed out (300s)")
        return False
    except Exception as e:
        log.warning(f"Scraper error: {e}")
        return False
    finally:
        _scraper_lock.release()


def _background_loop():
    """Periodically refresh data."""
    time.sleep(10)  # initial delay
    while True:
        try:
            _run_scraper()
            cleanup(30)  # keep 30 days
        except Exception as e:
            log.error(f"Background loop error: {e}")
        time.sleep(REFRESH_INTERVAL)


def _data_age_seconds():
    """How old is the quota data file?"""
    if not QUOTA_FILE.exists():
        return float("inf")
    try:
        data = json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
        ts = data.get("last_updated")
        if ts:
            dt = datetime.fromisoformat(ts)
            return (datetime.now(timezone.utc) - dt).total_seconds()
    except:
        pass
    return (time.time() - QUOTA_FILE.stat().st_mtime)


# ─── Routes ──────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_file(WEB_DIR / "index.html")


@app.route("/api/data")
def get_data():
    # If data is very stale, trigger async refresh
    age = _data_age_seconds()
    if age > STALE_THRESHOLD:
        threading.Thread(target=_run_scraper, daemon=True).start()

    if QUOTA_FILE.exists():
        return jsonify(json.loads(QUOTA_FILE.read_text(encoding="utf-8")))
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
    """Manual refresh — runs scraper synchronously."""
    ok = _run_scraper()
    if ok:
        data = {}
        if QUOTA_FILE.exists():
            data = json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
        return jsonify({"status": "ok", "data": data})
    return jsonify({"status": "error", "error": "Scraper failed"}), 500


@app.route("/api/history/<provider>")
def api_history(provider):
    """Get history for a provider."""
    field = request.args.get('field')
    hours = int(request.args.get('hours', 24))
    hours = min(hours, 720)  # Max 30 days
    data = get_history(provider, field, hours)
    return jsonify(data)


@app.route("/api/refresh/<provider>", methods=["POST"])
def refresh_provider(provider):
    """Refresh a single provider."""
    if not _ensure_chrome():
        return jsonify({"status": "error", "error": "No Chrome available"}), 500
    try:
        result = subprocess.run(
            ["python3", str(SCRAPER_SCRIPT), "-p", provider],
            capture_output=True, text=True, timeout=120,
            cwd=str(PROJECT_DIR),
        )
        if result.returncode == 0:
            data = {}
            if QUOTA_FILE.exists():
                data = json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
                try:
                    record_snapshot(data)
                except Exception as e:
                    log.warning(f"History record failed: {e}")
            # Broadcast to all SSE clients
            _sse_broadcast("provider_refresh", {"provider": provider, "data": data})
            return jsonify({"status": "ok", "data": data.get(provider, {})})
        return jsonify({"status": "error", "error": result.stderr[:200] or "Scraper failed"}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "error": "Timeout"}), 504
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/events")
def sse_stream():
    """SSE endpoint — clients connect here for live updates."""
    q = queue.Queue(maxsize=50)
    with _sse_lock:
        _sse_clients.append(q)

    def generate():
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield msg
                except queue.Empty:
                    yield ": keepalive\n\n"  # prevent timeout
        except GeneratorExit:
            pass
        finally:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/api/screenshots/<path:filename>")
def get_screenshot(filename):
    return send_from_directory(str(SCREENSHOT_DIR), filename)


@app.route("/api/screenshots")
def list_screenshots():
    if not SCREENSHOT_DIR.exists():
        return jsonify([])
    files = sorted(SCREENSHOT_DIR.glob("*.png"), key=lambda f: f.stat().st_mtime, reverse=True)
    return jsonify([{"name": f.name, "size": f.stat().st_size} for f in files[:30]])


# ─── Main ────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Start background scraper thread
    t = threading.Thread(target=_background_loop, daemon=True)
    t.start()
    log.info(f"Dashboard server starting on :8502 (refresh every {REFRESH_INTERVAL//3600}h)")
    app.run(host="0.0.0.0", port=8502, debug=False)
