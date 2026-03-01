#!/usr/bin/env python3
"""
LLM Quota Dashboard Scraper — Parallel CDP (multi-tab)

Opens one tab per provider, scrapes all simultaneously.
~3-4x faster than sequential.

Usage:
  python scrape_dashboards_parallel.py
  python scrape_dashboards_parallel.py -p zai anthropic
  python scrape_dashboards_parallel.py --json --debug
"""

import argparse
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import websocket

CDP_PORT = 18800
PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"
QUOTA_FILE = DATA_DIR / "quota_data.json"

now_iso = lambda: datetime.now(timezone.utc).isoformat()
DEBUG = False


# ─── Per-tab CDP Session ─────────────────────────────────────────

class CDPTab:
    """One CDP tab via browser-level WS. Each instance creates+controls its own tab."""

    def __init__(self, browser_ws_url: str):
        self.browser_ws_url = browser_ws_url
        self.ws = None
        self.session_id = None
        self.target_id = None
        self._msg_id = 0
        self._owned_tab = False

    def open(self):
        self.ws = websocket.create_connection(self.browser_ws_url, timeout=30, suppress_origin=True)
        # Create a new tab
        resp = self._send_browser("Target.createTarget", {"url": "about:blank", "background": True})
        self.target_id = resp["result"]["targetId"]
        self._owned_tab = True
        # Attach
        resp = self._send_browser("Target.attachToTarget", {"targetId": self.target_id, "flatten": True})
        self.session_id = resp["result"]["sessionId"]
        self._send_session("Page.enable")
        # Set viewport large enough for wide dashboards
        self._send_session("Emulation.setDeviceMetricsOverride", {
            "width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False
        })
        return self

    def close(self):
        if self._owned_tab and self.target_id:
            try:
                self._send_browser("Target.closeTarget", {"targetId": self.target_id})
            except:
                pass
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

    def _next_id(self):
        self._msg_id += 1
        return self._msg_id

    def _send_browser(self, method, params=None):
        mid = self._next_id()
        msg = {"id": mid, "method": method}
        if params:
            msg["params"] = params
        self.ws.send(json.dumps(msg))
        return self._recv(mid)

    def _send_session(self, method, params=None):
        mid = self._next_id()
        msg = {"id": mid, "method": method, "sessionId": self.session_id}
        if params:
            msg["params"] = params
        self.ws.send(json.dumps(msg))
        return self._recv(mid)

    def _recv(self, mid, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.ws.settimeout(5)
                resp = json.loads(self.ws.recv())
                if resp.get("id") == mid:
                    return resp
            except websocket.WebSocketTimeoutException:
                continue
        return {"error": {"message": "CDP timeout"}}

    def navigate(self, url):
        self._send_session("Page.navigate", {"url": url})

    def evaluate(self, js):
        resp = self._send_session("Runtime.evaluate", {"expression": js, "returnByValue": True})
        return resp.get("result", {}).get("result", {}).get("value", "")

    def get_text(self):
        return self.evaluate("document.body?.innerText || ''")

    def wait_for_text(self, keywords, timeout=12):
        deadline = time.time() + timeout
        text = ""
        while time.time() < deadline:
            text = self.get_text()
            text_lower = text.lower()
            if any(kw.lower() in text_lower for kw in keywords):
                return True, text
            time.sleep(0.5)
        return False, text

    def click_by_text(self, text, selector="[role=tab]", timeout=8):
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

    def mouse_move(self, x, y):
        self._send_session("Input.dispatchMouseEvent",
                           {"type": "mouseMoved", "x": x, "y": y, "pointerType": "mouse"})

    def check_login(self, text: str) -> bool:
        """Return True if page looks like a login/auth page."""
        login_keywords = ["sign in", "log in", "login", "sign up", "create account",
                          "forgot password", "authenticate", "登录", "登入", "注册"]
        text_lower = text.lower()
        return any(kw in text_lower for kw in login_keywords)


# ─── Provider Scrapers (same logic, takes CDPTab instead) ────────

def scrape_zai(tab: CDPTab) -> dict:
    tab.navigate("https://z.ai/manage-apikey/subscription")
    tab.click_by_text("Usage", "[role=tab]", timeout=10)
    time.sleep(0.3)
    found, text = tab.wait_for_text(["hours quota", "total tokens"], timeout=10)
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
    m = re.search(r'(Coding\s*Plan|Free\s*Plan|Pro\s*Plan)', text, re.I)
    if m:
        data["plan"] = m.group(1).strip()
    return {"status": "success", "method": "cdp_parallel", "data": data, "last_checked": now_iso()}


def scrape_dashscope(tab: CDPTab) -> dict:
    tab.navigate("https://modelstudio.console.alibabacloud.com/ap-southeast-1/?tab=dashboard#/efm/coding_plan")
    found, text = tab.wait_for_text(["coding plan", "套餐用量", "剩余天数",
                                      "remaining days", "USD/month", "美元/月"], timeout=18)
    # DashScope table renders slowly — wait for data to fully load before hover
    time.sleep(3)
    text = tab.get_text()  # re-read after delay
    if DEBUG:
        print(f"    [dashscope] {len(text)}c found={found}")
    data = {"provider": "dashscope"}
    # Plan name (works for both CN/EN — "Coding Plan" appears in both)
    m = re.search(r'(Coding Plan\s*\w*)', text)
    if m:
        data["plan"] = m.group(1).strip()
    # CN: "50美元/月" | EN: "50 USD/month" or "$50/month"
    m = re.search(r'(\d+)\s*(?:美元/月|USD/month)', text, re.I)
    if not m:
        m = re.search(r'\$(\d+)/month', text, re.I)
    if m:
        data["price_usd_month"] = int(m.group(1))
    # CN: "26天" | EN: "26 days"
    m = re.search(r'(\d+)\s*(?:天|days?)\b', text, re.I)
    if m:
        data["remaining_days"] = int(m.group(1))
    # CN: "10%\n每周" | EN: "10%\nEvery Week" or "10%\nWeekly"
    m = re.search(r'(\d+)%\s*\n\s*(?:每周|Every\s*Week|Weekly)', text, re.I)
    if m:
        data["weekly_used_pct"] = int(m.group(1))
    # CN: "开始时间" | EN: "Start Time"
    m = re.search(r'(?:开始时间|Start\s*Time)\s*\n\s*([\d-]+\s+[\d:]+)', text, re.I)
    if m:
        data["start_time"] = m.group(1).strip()
    m = re.search(r'(?:结束时间|End\s*Time)\s*\n\s*([\d-]+\s+[\d:]+)', text, re.I)
    if m:
        data["end_time"] = m.group(1).strip()

    # Hover popover — find the usage cell (CN: 每周, EN: Week/weekly)
    bbox_js = """(() => {
        const tds = document.querySelectorAll('td');
        for (const td of tds) {
            const t = td.textContent.toLowerCase();
            if (t.includes('%') && (t.includes('周') || t.includes('week'))) {
                const r = td.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    return JSON.stringify({x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
                }
            }
        }
        return null;
    })()"""
    bbox_raw = tab.evaluate(bbox_js)
    if DEBUG:
        print(f"    [dashscope] hover target: {bbox_raw}")
    if bbox_raw and bbox_raw != "null":
        try:
            bbox = json.loads(bbox_raw)
            tab.mouse_move(0, 0)
            time.sleep(0.3)
            tab.mouse_move(int(bbox["x"]), int(bbox["y"]))
            time.sleep(2.5)
        except Exception as e:
            if DEBUG:
                print(f"    [dashscope] hover error: {e}")

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
            const items = [];
            labels.forEach((label, i) => {
                items.push({label: label.textContent.trim(), value: values[i]?.textContent?.trim() || ''});
            });
            result[period] = {refresh: refreshEl?.textContent?.trim() || '', items: items};
        });
        return JSON.stringify(result);
    })()"""
    popover_raw = tab.evaluate(popover_js)
    if popover_raw and popover_raw != "null":
        try:
            popover = json.loads(popover_raw)
            # Map both CN and EN period names to prefix
            period_map = {
                "每5小时": "5h", "Every 5": "5h",
                "每周": "weekly", "Weekly": "weekly",
                "每订阅月": "monthly", "Every Subscription": "monthly", "Monthly": "monthly",
            }
            for period_name, pdata in popover.items():
                prefix = None
                for key, pfx in period_map.items():
                    if key.lower() in period_name.lower():
                        prefix = pfx
                        break
                if not prefix:
                    continue
                if pdata.get("refresh"):
                    data[f"{prefix}_refresh"] = pdata["refresh"]
                for item in pdata.get("items", []):
                    label = item.get("label", "")
                    val = item.get("value", "")
                    val_clean = val.replace(",", "").replace("%", "").strip()
                    if not val_clean.isdigit():
                        continue
                    num = int(val_clean)
                    if label in ("总量", "Total"):
                        data[f"{prefix}_total"] = num
                    elif label in ("使用率", "Usage rate"):
                        data[f"{prefix}_used_pct"] = num
                    elif "%" in val:
                        # EN: duplicate "Used" label — the one with % is usage rate
                        data[f"{prefix}_used_pct"] = num
                    elif label in ("已使用", "Used"):
                        data[f"{prefix}_used"] = num
        except:
            pass
    return {"status": "success", "method": "cdp_parallel", "data": data, "last_checked": now_iso()}


def scrape_anthropic(tab: CDPTab) -> dict:
    tab.navigate("https://claude.ai/settings/usage")
    found, text = tab.wait_for_text(["% used", "monthly spend"], timeout=12)
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
    return {"status": "success", "method": "cdp_parallel", "data": data, "last_checked": now_iso()}


def scrape_kimi(tab: CDPTab) -> dict:
    tab.navigate("https://www.kimi.com/code/console?from=kfc_overview_topbar")
    # Wait for page — supports both EN and CN
    tab.wait_for_text(["weekly usage", "本周用量", "周使用"], timeout=15)
    time.sleep(3)
    found, text = tab.wait_for_text(["resets in", "后重置", "小时后"], timeout=15)
    if DEBUG:
        print(f"    [kimi] {len(text)}c found={found}")
    data = {"provider": "kimi"}
    m = re.search(r'(Allegretto|Presto|Andante|Moderato|Free)', text, re.I)
    if m:
        data["tier"] = m.group(1).strip()
    m = re.search(r'(K[\d.]+)', text)
    if m:
        data["model"] = m.group(1)
    # EN: "Weekly usage ... 51% Resets in 40 hours"
    m = re.search(r'Weekly\s*usage[\s\S]*?(-|\d+)%?\s*\n\s*Resets?\s*in\s*(.+)', text, re.I)
    if m:
        val = m.group(1)
        data["weekly_used_pct"] = 0 if val == "-" else int(val)
        data["weekly_reset"] = m.group(2).strip()
    # CN: "本周用量 ... 51% 40小时后重置"
    if "weekly_used_pct" not in data:
        m = re.search(r'(?:本周用量|周使用|每周用量)[\s\S]*?(-|\d+)%\s*\n?\s*(\d+)\s*小时后重置', text)
        if m:
            val = m.group(1)
            data["weekly_used_pct"] = 0 if val == "-" else int(val)
            data["weekly_reset"] = f"{m.group(2)} hours"
    # EN: "Rate limit ... 0% Resets in 2 hours"
    m = re.search(r'Rate\s*limit[\s\S]*?(-|\d+)%?\s*\n\s*Resets?\s*in\s*(.+)', text, re.I)
    if m:
        val = m.group(1)
        data["rate_limit_used_pct"] = 0 if val == "-" else int(val)
        data["rate_reset"] = m.group(2).strip()
    # CN: "频限明细 ... 0% 2小时后重置"
    if "rate_limit_used_pct" not in data:
        m = re.search(r'(?:频限明细|速率限制)[\s\S]*?(-|\d+)%\s*\n?\s*(\d+)\s*小时后重置', text)
        if m:
            val = m.group(1)
            data["rate_limit_used_pct"] = 0 if val == "-" else int(val)
            data["rate_reset"] = f"{m.group(2)} hours"
    return {"status": "success", "method": "cdp_parallel", "data": data, "last_checked": now_iso()}


def scrape_minimax(tab: CDPTab) -> dict:
    tab.navigate("https://platform.minimax.io/user-center/payment/coding-plan")
    found, text = tab.wait_for_text(["% used", "available usage", "valid until",
                                      "可用额度", "有效期至", "已使用"], timeout=12)
    if DEBUG:
        print(f"    [minimax] {len(text)}c found={found}")
    data = {"provider": "minimax"}
    # EN/CN plan name
    m = re.search(r'((?:Plus|Starter|Pro|Enterprise)\s*[–\-]\s*\S+)', text)
    if m:
        data["plan"] = m.group(1).strip()
    # EN: "Available usage: 300 prompts / 5 hours"
    m = re.search(r'Available\s*usage:\s*(\d+)\s*prompts?\s*/\s*(\d+)\s*hours?', text, re.I)
    if m:
        data["prompts_per_window"] = int(m.group(1))
        data["window_hours"] = int(m.group(2))
    # CN: "可用额度: 300 次 / 5 小时" or "可用额度：300次/5小时"
    if "prompts_per_window" not in data:
        m = re.search(r'可用额度[：:]\s*(\d+)\s*次?\s*/\s*(\d+)\s*小时', text)
        if m:
            data["prompts_per_window"] = int(m.group(1))
            data["window_hours"] = int(m.group(2))
    # EN: "Valid until: 03/27/2026"
    m = re.search(r'Valid\s*until\s*:?\s*([\d/]+)', text, re.I)
    if m:
        data["valid_until"] = m.group(1).strip()
    # CN: "有效期至: 2026/03/27" or "有效期至 03/27/2026"
    if "valid_until" not in data:
        m = re.search(r'有效期至[：:]?\s*([\d/\-]+)', text)
        if m:
            data["valid_until"] = m.group(1).strip()
    # % used (EN + CN)
    m = re.search(r'(\d+)%\s*(?:Used|已使用)', text, re.I)
    if m:
        data["current_used_pct"] = int(m.group(1))
    m = re.search(r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*\(?UTC\)?', text)
    if m:
        data["current_window"] = f"{m.group(1)}-{m.group(2)} UTC"
    m = re.search(r'Resets?\s*in\s*([\d]+\s*hr\s*[\d]*\s*min|[\d]+\s*(?:hour|hr|min)s?)', text, re.I)
    if m:
        data["reset_in"] = m.group(1).strip()
    # CN: "X 小时后重置" or "剩余 X 小时"
    if "reset_in" not in data:
        m = re.search(r'(\d+)\s*小时后重置|剩余\s*(\d+)\s*小时', text)
        if m:
            hours = m.group(1) or m.group(2)
            data["reset_in"] = f"{hours} hr"
    return {"status": "success", "method": "cdp_parallel", "data": data, "last_checked": now_iso()}


PROVIDERS = {
    "zai":       {"name": "Z.AI",       "color": "🔵", "fn": scrape_zai},
    "dashscope": {"name": "DashScope",  "color": "🟠", "fn": scrape_dashscope},
    "anthropic": {"name": "Anthropic",  "color": "🟤", "fn": scrape_anthropic},
    "kimi":      {"name": "Kimi",       "color": "🟣", "fn": scrape_kimi},
    "minimax":   {"name": "MiniMax",    "color": "🟢", "fn": scrape_minimax},
}


def get_browser_ws_url(port=CDP_PORT):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5) as r:
        return json.loads(r.read())["webSocketDebuggerUrl"]


def scrape_one(key, browser_ws_url):
    """Scrape a single provider in its own tab."""
    prov = PROVIDERS[key]
    tab = CDPTab(browser_ws_url)
    t1 = time.time()
    try:
        tab.open()
        result = prov["fn"](tab)
        elapsed = time.time() - t1

        # Post-scrape login detection: if very few fields extracted, check page text
        data = result.get("data", {})
        real_fields = [k for k, v in data.items() if v is not None and v != "" and k != "provider"]
        if len(real_fields) < 2:
            text = tab.get_text()
            if tab.check_login(text):
                print(f"  {prov['color']} {prov['name']:15} 🔑 Need login ({elapsed:.1f}s)")
                return key, {"status": "need_login", "method": "cdp_parallel",
                             "message": f"Not logged in to {prov['name']}", "last_checked": now_iso()}

        n = len(real_fields)
        if n == 0:
            print(f"  {prov['color']} {prov['name']:15} ⚠️ 0 fields ({elapsed:.1f}s)")
            return key, {"status": "error", "method": "cdp_parallel",
                         "error": "No data extracted", "last_checked": now_iso()}
        print(f"  {prov['color']} {prov['name']:15} ✅ {n} fields ({elapsed:.1f}s)")
        return key, result
    except Exception as e:
        elapsed = time.time() - t1
        # Also check if it's a login issue
        try:
            text = tab.get_text()
            if tab.check_login(text):
                print(f"  {prov['color']} {prov['name']:15} 🔑 Need login ({elapsed:.1f}s)")
                return key, {"status": "need_login", "method": "cdp_parallel",
                             "message": f"Not logged in to {prov['name']}", "last_checked": now_iso()}
        except:
            pass
        print(f"  {prov['color']} {prov['name']:15} ❌ {str(e)[:80]} ({elapsed:.1f}s)")
        return key, {"status": "error", "method": "cdp_parallel", "message": str(e)[:200], "last_checked": now_iso()}
    finally:
        tab.close()


def load_existing():
    if QUOTA_FILE.exists():
        try:
            return json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return {}


def save_data(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    QUOTA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main():
    global DEBUG
    parser = argparse.ArgumentParser(description="Parallel CDP scraper (multi-tab)")
    parser.add_argument("--provider", "-p", nargs="+")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--cdp-port", type=int, default=CDP_PORT)
    args = parser.parse_args()
    DEBUG = args.debug

    targets = args.provider or list(PROVIDERS.keys())
    print(f"🔍 Scraping {len(targets)} provider(s) — CDP parallel, multi-tab")

    try:
        browser_ws_url = get_browser_ws_url(args.cdp_port)
    except Exception as e:
        print(f"❌ Cannot connect to CDP on port {args.cdp_port}: {e}")
        return

    t0 = time.time()
    results = {}

    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        futures = {pool.submit(scrape_one, key, browser_ws_url): key for key in targets if key in PROVIDERS}
        for future in as_completed(futures):
            key, result = future.result()
            results[key] = result

    existing = load_existing()
    for key, result in results.items():
        if result.get("status") == "success":
            existing[key] = result
        elif result.get("status") == "need_login":
            existing[key] = result
        else:
            # Keep last successful data, just add error info
            old = existing.get(key, {})
            if old.get("status") == "success":
                old["last_error"] = result.get("error", "scrape failed")
                old["last_error_time"] = now_iso()
                existing[key] = old
            else:
                existing[key] = result
    existing["last_updated"] = now_iso()
    save_data(existing)

    total = time.time() - t0

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False, default=str))

    print(f"\n⏱ {total:.0f}s total | {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
