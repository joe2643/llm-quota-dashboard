#!/usr/bin/env python3
"""
LLM Quota Dashboard Scraper — CDP Direct (no Playwright)

Single browser WS connection → attach to one tab → navigate sequentially.
Reuses existing tab, waits for data fields before extracting.

Usage:
  python scrape_dashboards.py                    # All providers
  python scrape_dashboards.py -p zai anthropic   # Specific
  python scrape_dashboards.py --json             # JSON output
  python scrape_dashboards.py --debug            # Show extracted text
"""

import argparse
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import websocket

# ─── Config ──────────────────────────────────────────────────────
CDP_PORT = 18800
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"

PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"
QUOTA_FILE = DATA_DIR / "quota_data.json"

now_iso = lambda: datetime.now(timezone.utc).isoformat()
DEBUG = False


# ─── CDP Session (browser-level WS + target attach) ─────────────

class CDPSession:
    """Lightweight CDP session via browser-level WebSocket."""
    
    def __init__(self, port: int = CDP_PORT):
        self.port = port
        self.ws = None
        self.session_id = None
        self.target_id = None
        self._msg_id = 0
    
    def connect(self):
        """Connect to browser WS and attach to a page tab."""
        # Get browser WS URL
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=5) as r:
            info = json.loads(r.read())
        ws_url = info["webSocketDebuggerUrl"]
        
        self.ws = websocket.create_connection(ws_url, timeout=10, suppress_origin=True)
        
        # Find a page target
        resp = self._send("Target.getTargets")
        pages = [t for t in resp["result"]["targetInfos"] if t["type"] == "page"]
        if not pages:
            raise RuntimeError("No page tabs found")
        
        self.target_id = pages[0]["targetId"]
        
        # Attach
        resp = self._send("Target.attachToTarget", {"targetId": self.target_id, "flatten": True})
        self.session_id = resp["result"]["sessionId"]
        
        # Enable Page domain
        self._send("Page.enable", session=True)
        
        return self
    
    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
    
    def _send(self, method: str, params: dict = None, session: bool = False) -> dict:
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method}
        if params:
            msg["params"] = params
        if session and self.session_id:
            msg["sessionId"] = self.session_id
        self.ws.send(json.dumps(msg))
        
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                self.ws.settimeout(5)
                resp = json.loads(self.ws.recv())
                if resp.get("id") == self._msg_id:
                    return resp
            except websocket.WebSocketTimeoutException:
                continue
        return {"error": {"message": "CDP timeout"}}
    
    def navigate(self, url: str) -> bool:
        """Navigate current tab to URL."""
        resp = self._send("Page.navigate", {"url": url}, session=True)
        if "error" in resp:
            return False
        return True
    
    def evaluate(self, js: str) -> str:
        """Evaluate JS in page context and return string result."""
        resp = self._send("Runtime.evaluate",
                          {"expression": js, "returnByValue": True},
                          session=True)
        return resp.get("result", {}).get("result", {}).get("value", "")
    
    def get_text(self) -> str:
        return self.evaluate("document.body?.innerText || ''")
    
    def wait_for_text(self, keywords: list[str], timeout: int = 12) -> tuple[bool, str]:
        """Poll until any keyword appears in page text."""
        deadline = time.time() + timeout
        text = ""
        while time.time() < deadline:
            text = self.get_text()
            text_lower = text.lower()
            if any(kw.lower() in text_lower for kw in keywords):
                return True, text
            time.sleep(0.5)
        return False, text
    
    def click_by_text(self, text: str, selector: str = "[role=tab]", timeout: int = 8) -> bool:
        """Poll-click element matching selector + text content."""
        js = f"""(() => {{
            const els = document.querySelectorAll('{selector}');
            for (const el of els) {{
                if (el.textContent.trim() === '{text}') {{ el.click(); return true; }}
            }}
            return false;
        }})()"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self.evaluate(js)
            if result is True or result == "true":
                return True
            time.sleep(0.5)
        return False
    
    def navigate_and_wait(self, url: str, keywords: list[str], timeout: int = 15) -> tuple[bool, str]:
        """Navigate to URL and wait for data keywords to appear."""
        self.navigate(url)
        return self.wait_for_text(keywords, timeout=timeout)


# ─── Provider Scrapers ───────────────────────────────────────────

def scrape_zai(cdp: CDPSession) -> dict:
    """Z.AI: subscription page → click Usage tab → extract quota"""
    
    cdp.navigate("https://z.ai/manage-apikey/subscription")
    
    # Wait for and click Usage tab
    cdp.click_by_text("Usage", "[role=tab]", timeout=10)
    time.sleep(0.3)
    
    # Wait for quota data
    found, text = cdp.wait_for_text(["hours quota", "total tokens"], timeout=10)
    
    if DEBUG:
        print(f"    [zai] {len(text)}c found={found}")
    
    data = {"provider": "zai"}
    
    m = re.search(r'(\d+)\s*Hours?\s*Quota\s*\n\s*(\d+)\s*\n\s*%', text)
    if m:
        data["5h_quota_used_pct"] = int(m.group(2))
    
    m = re.search(r'Weekly\s*Quota\s*\n\s*(\d+)\s*\n\s*%\s*\n\s*Used\s*\n\s*Reset\s*Time:\s*(.+)', text)
    if m:
        data["weekly_quota_used_pct"] = int(m.group(1))
        data["weekly_reset"] = m.group(2).strip()
    
    m = re.search(r'Monthly\s*Web\s*Search.*?Quota\s*\n\s*(\d+)\s*\n\s*%\s*\n\s*Used\s*\n\s*Reset\s*Time:\s*(.+)', text)
    if m:
        data["monthly_search_used_pct"] = int(m.group(1))
        data["monthly_search_reset"] = m.group(2).strip()
    
    m = re.search(r'Total\s*Tokens\s*\n\s*([\d,]+)', text)
    if m:
        data["total_tokens"] = int(m.group(1).replace(",", ""))
    
    m = re.search(r'(Coding\s*Plan|Free\s*Plan|Pro\s*Plan|Pro\s*plan)', text, re.I)
    if m:
        data["plan"] = m.group(1).strip()
    
    return {"status": "success", "method": "cdp_direct", "data": data, "last_checked": now_iso()}


def scrape_dashscope(cdp: CDPSession) -> dict:
    """DashScope: coding plan page. Reads hidden popover DOM for detailed usage."""
    
    cdp.navigate("https://modelstudio.console.alibabacloud.com/ap-southeast-1/?tab=dashboard#/efm/coding_plan")
    found, text = cdp.wait_for_text(["coding plan", "套餐用量", "剩余天数"], timeout=18)
    
    if DEBUG:
        print(f"    [dashscope] {len(text)}c found={found}")
    
    data = {"provider": "dashscope"}
    
    # Basic info from page text
    m = re.search(r'(Coding Plan\s*\w*)', text)
    if m:
        data["plan"] = m.group(1).strip()
    
    m = re.search(r'(\d+)美元/月', text)
    if m:
        data["price_usd_month"] = int(m.group(1))
    
    m = re.search(r'(\d+)天', text)
    if m:
        data["remaining_days"] = int(m.group(1))
    
    # Weekly % from basic page text (always available)
    m = re.search(r'(\d+)%\s*\n\s*每周', text)
    if m:
        data["weekly_used_pct"] = int(m.group(1))
    
    m = re.search(r'开始时间\s*\n\s*([\d-]+\s+[\d:]+)', text)
    if m:
        data["start_time"] = m.group(1).strip()
    m = re.search(r'结束时间\s*\n\s*([\d-]+\s+[\d:]+)', text)
    if m:
        data["end_time"] = m.group(1).strip()
    
    # Trigger popover via CDP mouse hover on the usage DATA cell (not header)
    # Must move mouse away first, then to target — triggers real browser events
    bbox_js = """(() => {
        const tds = document.querySelectorAll('td');
        for (const td of tds) {
            if (td.textContent.includes('%') && td.textContent.includes('每周')) {
                const r = td.getBoundingClientRect();
                return JSON.stringify({x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
            }
        }
        return null;
    })()"""
    bbox_raw = cdp.evaluate(bbox_js)
    if bbox_raw and bbox_raw != "null":
        try:
            bbox = json.loads(bbox_raw)
            cdp._send("Input.dispatchMouseEvent",
                      {"type": "mouseMoved", "x": 0, "y": 0, "pointerType": "mouse"}, session=True)
            time.sleep(0.1)
            cdp._send("Input.dispatchMouseEvent",
                      {"type": "mouseMoved", "x": bbox["x"], "y": bbox["y"], "pointerType": "mouse"}, session=True)
            time.sleep(1.5)
        except:
            pass
    
    # Read popover DOM (mounted after hover)
    popover_js = """(() => {
        const card = document.querySelector('[class*="dosage-details-card"]');
        if (!card) return null;
        
        const sections = card.querySelectorAll('[class*="content-section"]');
        const result = {};
        
        sections.forEach(section => {
            const titleEl = section.querySelector('[class*="form-title-text"]');
            const refreshEl = section.querySelector('[class*="form-title-info"]');
            const values = section.querySelectorAll('[class*="stat-item-value__"]');
            const labels = section.querySelectorAll('[class*="stat-item-label"]');
            
            if (!titleEl) return;
            const period = titleEl.textContent.trim();
            const entry = { refresh: refreshEl?.textContent?.trim() || '' };
            
            labels.forEach((label, i) => {
                const key = label.textContent.trim();
                const val = values[i]?.textContent?.trim() || '';
                entry[key] = val;
            });
            
            result[period] = entry;
        });
        
        return JSON.stringify(result);
    })()"""
    
    popover_raw = cdp.evaluate(popover_js)
    if popover_raw and popover_raw != "null":
        try:
            popover = json.loads(popover_raw)
            if DEBUG:
                print(f"    [dashscope popover] {json.dumps(popover, ensure_ascii=False)}")
            
            for period, prefix in [("每5小时", "5h"), ("每周", "weekly"), ("每订阅月", "monthly")]:
                if period not in popover:
                    continue
                p = popover[period]
                for cn_key, en_key in [("总量", "total"), ("已使用", "used")]:
                    val = p.get(cn_key, "").replace(",", "")
                    if val.isdigit():
                        data[f"{prefix}_{en_key}"] = int(val)
                rate = p.get("使用率", "").replace("%", "")
                if rate.isdigit():
                    data[f"{prefix}_used_pct"] = int(rate)
                if p.get("refresh"):
                    data[f"{prefix}_refresh"] = p["refresh"]
        except (json.JSONDecodeError, ValueError):
            pass
    
    return {"status": "success", "method": "cdp_direct", "data": data, "last_checked": now_iso()}


def scrape_anthropic(cdp: CDPSession) -> dict:
    """Anthropic: claude.ai/settings/usage"""
    
    cdp.navigate("https://claude.ai/settings/usage")
    found, text = cdp.wait_for_text(["% used", "monthly spend"], timeout=12)
    
    if DEBUG:
        print(f"    [anthropic] {len(text)}c found={found}")
    
    data = {"provider": "anthropic"}
    
    m = re.search(r'(Max|Pro|Free|Team)\s*plan', text, re.I)
    if m:
        data["plan"] = m.group(1).strip() + " plan"
    
    m = re.search(r'Current\s*session\s*\n\s*Resets?\s*in\s*(.+?)\n\s*(\d+)%\s*used', text)
    if m:
        data["session_reset"] = m.group(1).strip()
        data["session_used_pct"] = int(m.group(2))
    
    m = re.search(r'All\s*models\s*\n\s*Resets?\s*(.+?)\n\s*(\d+)%\s*used', text)
    if m:
        data["weekly_all_reset"] = m.group(1).strip()
        data["weekly_all_used_pct"] = int(m.group(2))
    
    m = re.search(r'Sonnet\s*only\s*\n\s*Resets?\s*(.+?)\n\s*(\d+)%\s*used', text)
    if m:
        data["weekly_sonnet_reset"] = m.group(1).strip()
        data["weekly_sonnet_used_pct"] = int(m.group(2))
    
    m = re.search(r'\$([\d.]+)\s*spent\s*\n\s*Resets?\s*(.+?)\n\s*(\d+)%\s*used', text)
    if m:
        data["extra_spent_usd"] = float(m.group(1))
        data["extra_reset"] = m.group(2).strip()
        data["extra_used_pct"] = int(m.group(3))
    
    m = re.search(r'\$([\d.]+)\s*\n\s*Monthly\s*spend\s*limit', text)
    if m:
        data["monthly_limit_usd"] = float(m.group(1))
    
    m = re.search(r'\$([\d.]+)\s*\n\s*Current\s*balance', text)
    if m:
        data["balance_usd"] = float(m.group(1))
    
    return {"status": "success", "method": "cdp_direct", "data": data, "last_checked": now_iso()}


def scrape_kimi(cdp: CDPSession) -> dict:
    """Kimi: code console — slow loader. '-' means 0% used (freshly reset)."""
    
    cdp.navigate("https://www.kimi.com/code/console?from=kfc_overview_topbar")
    found, text = cdp.wait_for_text(["resets in", "weekly usage"], timeout=25)
    
    if DEBUG:
        print(f"    [kimi] {len(text)}c found={found}")
    
    data = {"provider": "kimi"}
    
    m = re.search(r'(Allegretto|Presto|Andante|Moderato|Free)', text, re.I)
    if m:
        data["tier"] = m.group(1).strip()
    
    m = re.search(r'(K[\d.]+)', text)
    if m:
        data["model"] = m.group(1)
    
    # Kimi shows '-' when quota just reset (= 0% used), or a number like '50%'
    m = re.search(r'Weekly\s*usage[\s\S]*?(-|\d+)%?\s*\n\s*Resets?\s*in\s*(.+)', text, re.I)
    if m:
        val = m.group(1)
        data["weekly_used_pct"] = 0 if val == "-" else int(val)
        data["weekly_reset"] = m.group(2).strip()
    
    m = re.search(r'Rate\s*limit[\s\S]*?(-|\d+)%?\s*\n\s*Resets?\s*in\s*(.+)', text, re.I)
    if m:
        val = m.group(1)
        data["rate_limit_used_pct"] = 0 if val == "-" else int(val)
        data["rate_reset"] = m.group(2).strip()
    
    return {"status": "success", "method": "cdp_direct", "data": data, "last_checked": now_iso()}


def scrape_minimax(cdp: CDPSession) -> dict:
    """MiniMax: coding plan page"""
    
    cdp.navigate("https://platform.minimax.io/user-center/payment/coding-plan")
    found, text = cdp.wait_for_text(["% used", "available usage", "valid until"], timeout=12)
    
    if DEBUG:
        print(f"    [minimax] {len(text)}c found={found}")
    
    data = {"provider": "minimax"}
    
    m = re.search(r'((?:Plus|Starter|Pro|Enterprise)\s*[–\-]\s*\S+)', text)
    if m:
        data["plan"] = m.group(1).strip()
    
    m = re.search(r'Available\s*usage:\s*(\d+)\s*prompts?\s*/\s*(\d+)\s*hours?', text, re.I)
    if m:
        data["prompts_per_window"] = int(m.group(1))
        data["window_hours"] = int(m.group(2))
    
    m = re.search(r'Valid\s*until\s*:?\s*([\d/]+)', text, re.I)
    if m:
        data["valid_until"] = m.group(1).strip()
    
    m = re.search(r'(\d+)%\s*Used', text, re.I)
    if m:
        data["current_used_pct"] = int(m.group(1))
    
    m = re.search(r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*\(?UTC\)?', text)
    if m:
        data["current_window"] = f"{m.group(1)}-{m.group(2)} UTC"
    
    m = re.search(r'Resets?\s*in\s*([\d]+\s*hr\s*[\d]*\s*min|[\d]+\s*(?:hour|hr|min)s?)', text, re.I)
    if m:
        data["reset_in"] = m.group(1).strip()
    
    return {"status": "success", "method": "cdp_direct", "data": data, "last_checked": now_iso()}


# ─── Registry ────────────────────────────────────────────────────

PROVIDERS = {
    "zai":       {"name": "Z.AI",       "color": "🔵", "fn": scrape_zai},
    "dashscope": {"name": "DashScope",  "color": "🟠", "fn": scrape_dashscope},
    "anthropic": {"name": "Anthropic",  "color": "🟤", "fn": scrape_anthropic},
    "kimi":      {"name": "Kimi",       "color": "🟣", "fn": scrape_kimi},
    "minimax":   {"name": "MiniMax",    "color": "🟢", "fn": scrape_minimax},
}


# ─── Output ──────────────────────────────────────────────────────

def format_provider(key: str, result: dict) -> str:
    meta = PROVIDERS.get(key, {})
    color = meta.get("color", "•")
    name = meta.get("name", key)
    data = result.get("data", {})
    status = result.get("status", "error")
    
    if status != "success":
        return f"{color} {name} — ❌ {result.get('message', 'error')[:60]}"
    
    parts = [f"{color} {name}"]
    
    if data.get("plan"):
        parts.append(f"  📋 {data['plan']}")
    if data.get("tier"):
        parts.append(f"  🎵 {data['tier']}{' · ' + data['model'] if data.get('model') else ''}")
    
    for field, label in [
        ("5h_quota_used_pct", "5h Quota"), ("5h_used_pct", "5h"),
        ("session_used_pct", "Session"),
        ("weekly_used_pct", "Weekly"), ("weekly_quota_used_pct", "Weekly"),
        ("weekly_all_used_pct", "Weekly(all)"), ("weekly_sonnet_used_pct", "Sonnet"),
        ("monthly_used_pct", "Monthly"), ("monthly_search_used_pct", "Search"),
        ("rate_limit_used_pct", "Rate"),
        ("current_used_pct", "Current"), ("extra_used_pct", "Extra"),
    ]:
        val = data.get(field)
        if val is not None:
            rem = 100 - val
            bar = "█" * max(0, int(rem / 5)) + "░" * (20 - max(0, int(rem / 5)))
            alert = " ⚠️" if rem < 20 else ""
            parts.append(f"  [{bar}] {rem}% left — {label}{alert}")
    
    if data.get("extra_spent_usd") is not None and data.get("monthly_limit_usd") is not None:
        parts.append(f"  💰 ${data['extra_spent_usd']:.2f} / ${data['monthly_limit_usd']:.0f}")
    if data.get("balance_usd") is not None:
        parts.append(f"  💳 ${data['balance_usd']:.2f} balance")
    if data.get("price_usd_month") is not None:
        parts.append(f"  💰 ${data['price_usd_month']}/month")
    if data.get("total_tokens"):
        parts.append(f"  🔢 {data['total_tokens']:,} tokens")
    if data.get("remaining_days"):
        parts.append(f"  📅 {data['remaining_days']} days left")
    if data.get("prompts_per_window"):
        parts.append(f"  📊 {data['prompts_per_window']} / {data.get('window_hours','?')}h")
    
    return "\n".join(parts)


# ─── Main ────────────────────────────────────────────────────────

def load_existing() -> dict:
    if QUOTA_FILE.exists():
        try:
            return json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return {}


def save_data(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    QUOTA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main():
    global DEBUG
    
    parser = argparse.ArgumentParser(description="Scrape LLM dashboards (CDP direct, single tab)")
    parser.add_argument("--provider", "-p", nargs="+")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--cdp-port", type=int, default=CDP_PORT)
    args = parser.parse_args()
    
    DEBUG = args.debug
    
    if args.list:
        for k, v in PROVIDERS.items():
            print(f"  {v['color']} {v['name']:15} ({k})")
        return
    
    targets = args.provider or list(PROVIDERS.keys())
    
    print(f"🔍 Scraping {len(targets)} provider(s) — CDP direct, single tab")
    
    existing = load_existing()
    results = {}
    t0 = time.time()
    
    try:
        cdp = CDPSession(args.cdp_port).connect()
    except Exception as e:
        print(f"❌ Cannot connect: {e}")
        return
    
    try:
        for key in targets:
            if key not in PROVIDERS:
                print(f"  ⚠ Unknown: {key}")
                continue
            
            prov = PROVIDERS[key]
            t1 = time.time()
            
            try:
                result = prov["fn"](cdp)
                data = result.get("data", {})
                real_fields = [k for k, v in data.items() if v is not None and v != "" and k != "provider"]
                
                # Login detection
                if len(real_fields) < 2:
                    text = cdp.get_text()
                    login_kw = ["sign in", "log in", "login", "登录", "登入"]
                    if any(kw in text.lower() for kw in login_kw):
                        elapsed = time.time() - t1
                        print(f"  {prov['color']} {prov['name']:15} 🔑 Need login ({elapsed:.1f}s)")
                        results[key] = {"status": "need_login", "method": "cdp_direct",
                                        "message": f"Not logged in to {prov['name']}", "last_checked": now_iso()}
                        continue
                
                results[key] = result
                n = len(real_fields)
                elapsed = time.time() - t1
                print(f"  {prov['color']} {prov['name']:15} ✅ {n} fields ({elapsed:.1f}s)")
                
            except Exception as e:
                elapsed = time.time() - t1
                err = str(e)[:80]
                print(f"  {prov['color']} {prov['name']:15} ❌ {err} ({elapsed:.1f}s)")
                results[key] = {"status": "error", "method": "cdp_direct", "message": str(e)[:200], "last_checked": now_iso()}
        
        # Navigate back to blank
        try:
            cdp.navigate("about:blank")
        except:
            pass
    finally:
        cdp.close()
    
    existing.update(results)
    existing["last_updated"] = now_iso()
    save_data(existing)
    
    total = time.time() - t0
    
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"\n{'='*50}")
        for key in targets:
            if key in results:
                print(f"\n{format_provider(key, results[key])}")
        print(f"\n{'='*50}")
        print(f"⏱ {total:.0f}s total | {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
