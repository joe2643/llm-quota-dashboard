#!/usr/bin/env python3
"""
LLM Quota Checker - Browser-First, Config-Driven

Providers are defined in data/providers.json (not hardcoded).
First run: --setup to interactively add providers.
Agent integration: --add to add a provider (prompts for URL if unknown).

Usage:
  python check_quota.py --setup              # Interactive first-time setup
  python check_quota.py --add                # Add a new provider interactively
  python check_quota.py --add --name "X" --dashboard-url "https://..."
  python check_quota.py                      # Check all enabled providers
  python check_quota.py --login zai          # Manual browser login
  python check_quota.py --provider zai kimi  # Check specific providers
  python check_quota.py --api-only           # API-only mode
  python check_quota.py --list               # List configured providers
  python check_quota.py --disable zai        # Disable a provider
  python check_quota.py --enable zai         # Enable a provider
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

# ─── Paths ───────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_DIR = PROJECT_DIR / "output" / "screenshots"
PROVIDERS_FILE = DATA_DIR / "providers.json"
QUOTA_FILE = DATA_DIR / "quota_data.json"
BROWSER_PROFILE_DIR = Path.home() / ".llm-quota-browser"
CACHE_TTL_SECONDS = 3600

# ─── Provider Config Management ─────────────────────────────────

def load_providers() -> dict:
    """Load provider configs from JSON file."""
    if PROVIDERS_FILE.exists():
        try:
            data = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
            return data.get("providers", {})
        except:
            pass
    return {}


def save_providers(providers: dict):
    """Save provider configs to JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Preserve _meta if exists
    existing = {}
    if PROVIDERS_FILE.exists():
        try:
            existing = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
        except:
            pass
    
    meta = existing.get("_meta", {
        "version": 1,
        "description": "LLM provider configurations. Edit or use 'check_quota.py --add'.",
        "fields": {
            "name": "Display name",
            "dashboard_url": "URL to scrape (the page showing usage/balance)",
            "login_url": "Login URL (optional, defaults to dashboard_url)",
            "extra_pages": "Additional pages to scrape (optional list of URLs)",
            "api_url": "API endpoint for quota (optional fallback)",
            "env_var": "Env var for API key (optional)",
            "color": "Emoji for display",
            "enabled": "Whether to check this provider",
            "notes": "Notes about this provider"
        }
    })
    
    out = {"_meta": meta, "providers": providers}
    PROVIDERS_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")


def get_enabled_providers() -> dict:
    """Get only enabled providers."""
    return {k: v for k, v in load_providers().items() if v.get("enabled", True)}


# ─── Provider Templates ─────────────────────────────────────────
# These are suggestions when adding common providers.
# The user/agent can override URLs during setup.

TEMPLATES = {
    "openai": {
        "name": "OpenAI",
        "dashboard_url": "https://platform.openai.com/settings/organization/billing/overview",
        "login_url": "https://platform.openai.com/login",
        "color": "⬛",
        "notes": "Shows billing/usage",
    },
    "google": {
        "name": "Google AI (Gemini)",
        "dashboard_url": "https://aistudio.google.com/apikey",
        "login_url": "https://aistudio.google.com/",
        "color": "🔴",
        "notes": "API key management page",
    },
    "deepseek": {
        "name": "DeepSeek",
        "dashboard_url": "https://platform.deepseek.com/usage",
        "login_url": "https://platform.deepseek.com/sign_in",
        "color": "🟦",
        "notes": "Usage/balance page",
    },
    "groq": {
        "name": "Groq",
        "dashboard_url": "https://console.groq.com/settings/limits",
        "login_url": "https://console.groq.com/login",
        "color": "🟧",
        "notes": "Rate limits page",
    },
    "together": {
        "name": "Together AI",
        "dashboard_url": "https://api.together.ai/settings/billing",
        "login_url": "https://api.together.ai/signin",
        "color": "🟪",
        "notes": "Billing page",
    },
    "fireworks": {
        "name": "Fireworks AI",
        "dashboard_url": "https://fireworks.ai/account/billing",
        "login_url": "https://fireworks.ai/login",
        "color": "🔶",
        "notes": "Billing/usage page",
    },
    "mistral": {
        "name": "Mistral AI",
        "dashboard_url": "https://console.mistral.ai/billing/",
        "login_url": "https://console.mistral.ai/",
        "color": "🟧",
        "notes": "Billing page",
    },
    "cohere": {
        "name": "Cohere",
        "dashboard_url": "https://dashboard.cohere.com/billing",
        "login_url": "https://dashboard.cohere.com/login",
        "color": "🔷",
        "notes": "Billing/usage",
    },
}


# ─── Setup & Add Flows ──────────────────────────────────────────

def interactive_setup():
    """First-time setup: ask user which providers to add."""
    providers = load_providers()
    
    print("\n🔧 LLM Quota Dashboard — Setup")
    print("=" * 50)
    
    if providers:
        print(f"\n📋 You already have {len(providers)} provider(s) configured:")
        for k, v in providers.items():
            status = "✅" if v.get("enabled", True) else "⏸"
            print(f"   {status} {v.get('color', '•')} {v.get('name', k)} ({k})")
        print(f"\nAdd more? (or Ctrl+C to keep current config)\n")
    else:
        print("\nNo providers configured yet. Let's add some!\n")
    
    # Show templates
    print("📦 Available templates:")
    all_templates = {**TEMPLATES}
    # Don't show templates that are already configured
    for k in providers:
        all_templates.pop(k, None)
    
    if all_templates:
        for i, (key, tmpl) in enumerate(all_templates.items(), 1):
            print(f"   {i}. {tmpl.get('color', '•')} {tmpl['name']} — {tmpl.get('notes', '')}")
    
    print(f"   C. Custom provider (enter your own URL)")
    print(f"   D. Done\n")
    
    while True:
        choice = input("Add which? (number/C/D): ").strip()
        
        if choice.upper() == 'D':
            break
        elif choice.upper() == 'C':
            add_custom_provider(providers)
        else:
            try:
                idx = int(choice) - 1
                keys = list(all_templates.keys())
                if 0 <= idx < len(keys):
                    key = keys[idx]
                    tmpl = all_templates[key]
                    
                    # Let user confirm/modify
                    print(f"\n   Adding {tmpl['name']}:")
                    print(f"   Dashboard URL: {tmpl.get('dashboard_url', '?')}")
                    
                    url = input(f"   Dashboard URL (Enter to keep, or paste new): ").strip()
                    if url:
                        tmpl["dashboard_url"] = url
                    
                    tmpl["enabled"] = True
                    providers[key] = tmpl
                    save_providers(providers)
                    all_templates.pop(key)
                    print(f"   ✅ Added {tmpl['name']}")
                else:
                    print("   ⚠ Invalid number")
            except ValueError:
                print("   ⚠ Enter a number, C, or D")
    
    print(f"\n✅ Setup done! {len(providers)} provider(s) configured.")
    print(f"   Config: {PROVIDERS_FILE}")
    print(f"\n   Next: python check_quota.py --login all")
    print(f"   Then: python check_quota.py")


def add_custom_provider(providers: dict):
    """Add a custom provider interactively."""
    print("\n   📝 Add Custom Provider")
    
    key = input("   ID (short, no spaces, e.g. 'openrouter'): ").strip().lower()
    if not key:
        print("   ⚠ Cancelled")
        return
    
    if key in providers:
        print(f"   ⚠ '{key}' already exists. Use --enable/--disable to manage it.")
        return
    
    name = input(f"   Display name [{key.title()}]: ").strip() or key.title()
    dashboard_url = input("   Dashboard URL (the page showing quota/usage): ").strip()
    
    if not dashboard_url:
        print("   ⚠ Dashboard URL is required!")
        return
    
    login_url = input(f"   Login URL (Enter to auto-detect): ").strip() or None
    api_url = input(f"   API quota endpoint (Enter to skip): ").strip() or None
    env_var = input(f"   API key env var name (Enter to skip): ").strip() or None
    color = input(f"   Emoji [🔹]: ").strip() or "🔹"
    notes = input(f"   Notes (optional): ").strip() or ""
    
    provider = {
        "name": name,
        "dashboard_url": dashboard_url,
        "color": color,
        "enabled": True,
    }
    if login_url:
        provider["login_url"] = login_url
    if api_url:
        provider["api_url"] = api_url
    if env_var:
        provider["env_var"] = env_var
    if notes:
        provider["notes"] = notes
    
    providers[key] = provider
    save_providers(providers)
    print(f"   ✅ Added '{name}' ({key})")


def add_provider_noninteractive(key: str, name: str = None, dashboard_url: str = None,
                                login_url: str = None, api_url: str = None,
                                env_var: str = None, color: str = "🔹", notes: str = ""):
    """Add a provider non-interactively (for agent use)."""
    providers = load_providers()
    
    if key in providers:
        print(f"⚠ '{key}' already exists. Updating...")
    
    # Check template
    tmpl = TEMPLATES.get(key, {})
    
    provider = {
        "name": name or tmpl.get("name", key.title()),
        "dashboard_url": dashboard_url or tmpl.get("dashboard_url"),
        "color": color or tmpl.get("color", "🔹"),
        "enabled": True,
    }
    
    if not provider["dashboard_url"]:
        print(f"❌ No dashboard URL for '{key}'.")
        print(f"   Please provide: --dashboard-url <URL>")
        print(f"   Or ask the user for the quota/usage page URL.")
        return False
    
    if login_url or tmpl.get("login_url"):
        provider["login_url"] = login_url or tmpl.get("login_url")
    if api_url:
        provider["api_url"] = api_url
    if env_var:
        provider["env_var"] = env_var
    if notes or tmpl.get("notes"):
        provider["notes"] = notes or tmpl.get("notes", "")
    
    providers[key] = provider
    save_providers(providers)
    print(f"✅ Added provider '{provider['name']}' ({key})")
    print(f"   Dashboard: {provider['dashboard_url']}")
    return True


def list_providers():
    """List all configured providers."""
    providers = load_providers()
    
    if not providers:
        print("\n📋 No providers configured.")
        print("   Run: python check_quota.py --setup")
        return
    
    print(f"\n📋 Configured Providers ({len(providers)})")
    print("=" * 60)
    
    for key, p in providers.items():
        enabled = p.get("enabled", True)
        status = "✅" if enabled else "⏸"
        color = p.get("color", "•")
        name = p.get("name", key)
        url = p.get("dashboard_url", "?")
        api = "🔌" if p.get("api_url") else "  "
        
        print(f"  {status} {color} {name:20} {api}  {key}")
        print(f"      URL: {url}")
        if p.get("notes"):
            print(f"      Note: {p['notes']}")
    
    print(f"\n  Templates available (not yet added):")
    for k, t in TEMPLATES.items():
        if k not in providers:
            print(f"      {t.get('color', '•')} {t['name']} ({k})")


def toggle_provider(key: str, enabled: bool):
    """Enable or disable a provider."""
    providers = load_providers()
    if key not in providers:
        print(f"⚠ Provider '{key}' not found. Available: {', '.join(providers.keys())}")
        return
    providers[key]["enabled"] = enabled
    save_providers(providers)
    print(f"{'✅ Enabled' if enabled else '⏸ Disabled'} {providers[key].get('name', key)}")


# ─── Utility ─────────────────────────────────────────────────────

def load_cached_data() -> dict:
    if QUOTA_FILE.exists():
        try:
            return json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return {}


def save_quota_data(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    QUOTA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def is_cache_valid(ts: str) -> bool:
    try:
        cached = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - cached).total_seconds() < CACHE_TTL_SECONDS
    except:
        return False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Browser Helpers ─────────────────────────────────────────────

def get_context(playwright, headless=True):
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_PROFILE_DIR),
        headless=headless,
        viewport={"width": 1440, "height": 900},
        locale="zh-CN",
        timezone_id="Asia/Hong_Kong",
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        ignore_https_errors=True,
    )


def take_screenshot(page, name: str, timeout: int = 15000) -> str:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"{name}_{ts}.png"
    page.screenshot(path=str(path), full_page=False, timeout=timeout)
    return str(path)


def page_text(page) -> str:
    try:
        return page.evaluate("() => document.body?.innerText || ''")
    except:
        return ""


def is_login_page(page) -> bool:
    try:
        url = page.url.lower()
        if any(k in url for k in ["login", "signin", "auth", "sso"]):
            return True
        text = page_text(page).lower()
        if len(text) < 800 and any(k in text for k in ["登录", "登錄", "log in", "sign in", "密码", "password"]):
            return True
        login_prompts = ["登录以使用", "请登录", "请先登录", "sign in to continue",
                         "log in to continue", "please sign in", "please log in",
                         "登录后可使用", "需要登录", "sign in to your account",
                         "log in to your account"]
        if any(kw in text for kw in login_prompts):
            return True
        return False
    except:
        return False


def extract_page_data(page) -> dict:
    try:
        return page.evaluate("""() => {
            const result = {};
            const text = document.body.innerText || '';
            
            const ratios = [];
            const ratioRe = /(\\d[\\d,]*\\.?\\d*)\\s*\\/\\s*(\\d[\\d,]*\\.?\\d*)/g;
            let m;
            while ((m = ratioRe.exec(text)) !== null) {
                ratios.push({used: m[1], total: m[2], context: text.substring(Math.max(0, m.index-30), m.index+m[0].length+30).trim()});
            }
            if (ratios.length) result.ratios = ratios;
            
            const pcts = [];
            const pctRe = /(\\d+\\.?\\d*)\\s*%/g;
            while ((m = pctRe.exec(text)) !== null) {
                pcts.push({value: parseFloat(m[1]), context: text.substring(Math.max(0, m.index-30), m.index+m[0].length+30).trim()});
            }
            if (pcts.length) result.percentages = pcts;
            
            const amounts = [];
            const curRe = /[\\$¥￥]\\s*(\\d[\\d,]*\\.?\\d*)/g;
            while ((m = curRe.exec(text)) !== null) {
                amounts.push({value: m[0], context: text.substring(Math.max(0, m.index-30), m.index+m[0].length+30).trim()});
            }
            const curRe2 = /(\\d[\\d,]*\\.?\\d*)\\s*元/g;
            while ((m = curRe2.exec(text)) !== null) {
                amounts.push({value: m[0], context: text.substring(Math.max(0, m.index-30), m.index+m[0].length+30).trim()});
            }
            if (amounts.length) result.amounts = amounts;
            
            const bars = [];
            document.querySelectorAll('[role="progressbar"], [class*="progress"], [class*="Progress"]').forEach((el) => {
                const style = el.getAttribute('style') || '';
                const wm = style.match(/width:\\s*(\\d+)/);
                const aria = el.getAttribute('aria-valuenow');
                if (wm || aria) bars.push({width: wm?.[1], aria: aria, text: el.textContent?.trim()?.substring(0, 50)});
            });
            if (bars.length) result.progress_bars = bars;
            
            return result;
        }""")
    except Exception as e:
        return {"error": str(e)}


def extract_hints(text: str) -> dict:
    hints = {"quota": [], "usage": [], "balance": []}
    for line in text.split('\n'):
        line = line.strip()
        if not line or len(line) > 120:
            continue
        ll = line.lower()
        if any(k in ll for k in ['余额', '剩余', 'balance', 'remaining', 'credit', '额度']):
            hints["balance"].append(line)
        elif any(k in ll for k in ['已用', '使用', 'usage', 'used', '消耗', 'consumed']):
            hints["usage"].append(line)
        elif any(k in ll for k in ['quota', '配额', '限额', 'limit', 'rate']):
            hints["quota"].append(line)
    return {k: v for k, v in hints.items() if v}


# ─── Generic Scraper ─────────────────────────────────────────────

def scrape_provider(page, key: str, config: dict) -> dict:
    """Generic browser scraper for any provider."""
    dashboard_url = config.get("dashboard_url")
    if not dashboard_url:
        return {"status": "error", "message": "No dashboard URL configured"}
    
    # Navigate
    try:
        page.goto(dashboard_url, timeout=30000, wait_until="domcontentloaded")
    except Exception as e:
        if page.url and page.url != "about:blank":
            pass  # Continue with partial load
        else:
            return {"status": "error", "message": f"Navigation failed: {str(e)[:80]}"}
    
    page.wait_for_timeout(2500)
    
    if is_login_page(page):
        return {"status": "need_login", "message": f"Not logged in to {config.get('name', key)}"}
    
    page.wait_for_timeout(1500)
    
    shot = take_screenshot(page, key)
    text = page_text(page)
    data = extract_page_data(page)
    hints = extract_hints(text)
    
    result = {
        "status": "success",
        "method": "browser",
        "screenshot": shot,
        "last_checked": now_iso(),
        "page_url": page.url,
        "raw_text_snippet": text[:600],
    }
    
    if data and not data.get("error"):
        result["page_data"] = data
    if hints:
        result["hints"] = hints
    
    # Scrape extra pages if configured
    extra_pages = config.get("extra_pages", [])
    for i, extra_url in enumerate(extra_pages):
        try:
            page.goto(extra_url, timeout=15000)
            page.wait_for_timeout(2500)
            
            if not is_login_page(page):
                extra_shot = take_screenshot(page, f"{key}_extra{i}")
                extra_text = page_text(page)
                extra_data = extract_page_data(page)
                extra_hints = extract_hints(extra_text)
                
                result[f"extra_page_{i}"] = {
                    "url": extra_url,
                    "screenshot": extra_shot,
                    "page_data": extra_data if not extra_data.get("error") else None,
                    "hints": extra_hints or None,
                    "raw_text_snippet": extra_text[:400],
                }
        except:
            pass
    
    return result


# ─── API Fallbacks ──────────────────────────────────────────────

def api_check(key: str, config: dict) -> Optional[dict]:
    """Try API-based quota check if api_url is configured."""
    api_url = config.get("api_url")
    env_var = config.get("env_var")
    
    if not api_url or not env_var:
        return None
    
    api_key = os.environ.get(env_var)
    if not api_key:
        return None
    
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get(api_url, headers=headers, timeout=30)
        
        if resp.status_code == 200:
            # Try to parse as JSON
            try:
                data = resp.json()
                
                # Z.AI specific parsing
                if data.get("success") and data.get("data", {}).get("limits"):
                    limits = data["data"]["limits"]
                    time_limit = next((l for l in limits if l.get("type") == "TIME_LIMIT" and l.get("unit") == 5), None)
                    token_limit = next((l for l in limits if l.get("type") == "TOKENS_LIMIT" and l.get("unit") == 6), None)
                    active = time_limit or token_limit
                    
                    if active:
                        pct_used = active.get("percentage", 0)
                        reset_ts = active.get("nextResetTime", 0)
                        return {
                            "status": "success",
                            "method": "api",
                            "5h_window": {
                                "quota_percent": 100 - pct_used,
                                "usage_percent": pct_used,
                                "requests_used": active.get("usage"),
                                "requests_limit": active.get("number"),
                                "reset_at": datetime.fromtimestamp(reset_ts / 1000, tz=timezone.utc).isoformat() if reset_ts else None,
                            },
                            "last_checked": now_iso(),
                        }
                
                # Generic: API accessible
                return {
                    "status": "success",
                    "method": "api",
                    "note": "API key valid",
                    "raw_response_snippet": str(data)[:200],
                    "last_checked": now_iso(),
                }
            except:
                return {
                    "status": "success",
                    "method": "api",
                    "note": f"API returned HTTP {resp.status_code}",
                    "last_checked": now_iso(),
                }
        
        return {"status": "error", "method": "api", "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "method": "api", "message": str(e)[:80]}


# ─── Login Flow ──────────────────────────────────────────────────

def manual_login(provider_key: str):
    from playwright.sync_api import sync_playwright
    
    providers = load_providers()
    if provider_key not in providers:
        print(f"⚠ Provider '{provider_key}' not found.")
        print(f"   Available: {', '.join(providers.keys())}")
        return
    
    config = providers[provider_key]
    url = config.get("login_url", config.get("dashboard_url"))
    
    print(f"\n🔑 Opening {config.get('name', provider_key)}...")
    print(f"   URL: {url}")
    print(f"   Log in, then close the browser.\n")
    
    with sync_playwright() as p:
        ctx = get_context(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, timeout=30000)
        
        try:
            page.wait_for_event("close", timeout=300000)
        except:
            pass
        
        try:
            page2 = ctx.new_page()
            page2.goto(config.get("dashboard_url", url), timeout=15000)
            page2.wait_for_timeout(3000)
            if not is_login_page(page2):
                print(f"   ✅ {config.get('name', provider_key)} login saved!")
            else:
                print(f"   ⚠ Still on login page — try again?")
            page2.close()
        except:
            print(f"   ℹ Cookies saved. Will verify on next check.")
        
        ctx.close()


# ─── Main Check ─────────────────────────────────────────────────

def check_all(provider_keys=None, api_only=False):
    from playwright.sync_api import sync_playwright
    
    all_providers = load_providers()
    
    if not all_providers:
        print("❌ No providers configured!")
        print("   Run: python check_quota.py --setup")
        return {}
    
    # Filter
    if provider_keys:
        targets = {k: all_providers[k] for k in provider_keys if k in all_providers}
        missing = [k for k in provider_keys if k not in all_providers]
        if missing:
            print(f"⚠ Unknown providers: {', '.join(missing)}")
            print(f"   Available: {', '.join(all_providers.keys())}")
    else:
        targets = get_enabled_providers()
    
    if not targets:
        print("❌ No providers to check. Use --setup or --enable.")
        return {}
    
    results = {}
    cached = load_cached_data()
    
    ctx = None
    pw = None
    
    if not api_only:
        try:
            pw = sync_playwright().start()
            ctx = get_context(pw, headless=True)
        except Exception as e:
            print(f"⚠ Browser failed: {e}")
            print("  Falling back to API-only")
            api_only = True
    
    try:
        for key, config in targets.items():
            name = config.get("name", key)
            color = config.get("color", "•")
            
            print(f"\n{'='*45}")
            print(f"📋 {color} {name}")
            
            # Cache check
            if key in cached and is_cache_valid(cached[key].get("last_checked", "")):
                print(f"  💾 Cached")
                results[key] = cached[key]
                continue
            
            result = None
            
            # 1) Browser scrape
            if not api_only and ctx:
                print(f"  🌐 Browser scraping...")
                page = ctx.new_page()
                try:
                    result = scrape_provider(page, key, config)
                except Exception as e:
                    try:
                        take_screenshot(page, f"{key}_error")
                    except:
                        pass
                    result = {"status": "error", "method": "browser", "message": str(e)[:80]}
                finally:
                    page.close()
                
                if result.get("status") == "need_login":
                    print(f"    🔑 Need login → python check_quota.py --login {key}")
                elif result.get("status") == "success":
                    print(f"    ✅ Browser OK")
            
            # 2) API (always try if available — merge with browser data)
            api_result = api_check(key, config)
            if api_result:
                if result and result.get("status") == "success":
                    # Browser worked: merge API as extra structured data
                    result["api_data"] = api_result
                elif api_result.get("status") == "success":
                    # Browser failed: use API as primary
                    if result and result.get("status") == "need_login":
                        api_result["browser_status"] = "need_login"
                    result = api_result
                print(f"    {'✅' if api_result.get('status') == 'success' else '❌'} API: {api_result.get('status')}")
            
            if result is None:
                result = {"status": "error", "method": "none", "message": "No method available", "last_checked": now_iso()}
            
            results[key] = result
    
    finally:
        try:
            if ctx:
                ctx.close()
        except:
            pass
        try:
            if pw:
                pw.stop()
        except:
            pass
    
    results["last_updated"] = now_iso()
    return results


# ─── Output ──────────────────────────────────────────────────────

def format_results(results: dict) -> str:
    providers = load_providers()
    lines = ["\n📊 LLM Quota Dashboard", "=" * 50]
    
    for key, config in providers.items():
        data = results.get(key)
        if not data:
            continue
        
        status = data.get("status", "unknown")
        method = data.get("method", "?")
        name = config.get("name", key)
        icon = config.get("color", "•")
        
        if status == "success":
            info = []
            
            for src in [data, data.get("api_data", {})]:
                if "5h_window" in (src or {}):
                    w = src["5h_window"]
                    pct = w.get("quota_percent", 0)
                    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                    alert = " ⚠️" if pct < 20 else ""
                    info.append(f"[{bar}] {pct:.0f}%{alert}")
                    break
            
            pd = data.get("page_data", {})
            if pd.get("amounts"):
                for a in pd["amounts"][:2]:
                    info.append(f"💰 {a['value']}")
            
            hints = data.get("hints", {})
            for cat in ["balance", "quota", "usage"]:
                for h in hints.get(cat, [])[:1]:
                    info.append(f"💬 {h[:60]}")
            
            if not info:
                info.append("✓ Dashboard accessible")
            
            lines.append(f"\n{icon} {name} [{method}]")
            for p in info:
                lines.append(f"   {p}")
        
        elif status == "need_login":
            lines.append(f"\n{icon} {name} — 🔑 Need login")
        
        else:
            msg = data.get("message", "Unknown")
            lines.append(f"\n{icon} {name} — ❌ {msg[:50]}")
    
    lines.append(f"\n{'='*50}")
    lines.append(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    need = [k for k, v in results.items() if isinstance(v, dict) and v.get("status") == "need_login"]
    if need:
        lines.append(f"\n💡 Login: python check_quota.py --login {' | '.join(need)}")
    
    return "\n".join(lines)


# ─── CLI ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LLM Quota Checker (Browser-First, Config-Driven)")
    
    # Modes
    parser.add_argument("--setup", action="store_true", help="Interactive first-time setup")
    parser.add_argument("--add", action="store_true", help="Add a new provider")
    parser.add_argument("--list", action="store_true", help="List configured providers")
    parser.add_argument("--login", nargs="?", const="all", help="Manual login (provider key or 'all')")
    parser.add_argument("--enable", help="Enable a provider")
    parser.add_argument("--disable", help="Disable a provider")
    
    # Add options
    parser.add_argument("--name", help="Provider display name (for --add)")
    parser.add_argument("--dashboard-url", help="Dashboard URL (for --add)")
    parser.add_argument("--login-url", help="Login URL (for --add)")
    parser.add_argument("--api-url", help="API URL (for --add)")
    parser.add_argument("--env-var", help="Env var name (for --add)")
    parser.add_argument("--key", help="Provider key/ID (for --add)")
    
    # Check options
    parser.add_argument("--provider", "-p", nargs="+", help="Check specific providers")
    parser.add_argument("--api-only", action="store_true", help="API-only mode")
    parser.add_argument("--no-cache", action="store_true", help="Ignore cache")
    parser.add_argument("--json", action="store_true", help="JSON output")
    
    args = parser.parse_args()
    
    # Setup
    if args.setup:
        interactive_setup()
        return
    
    # Add
    if args.add:
        if args.key or args.dashboard_url:
            key = args.key or (args.name or "custom").lower().replace(" ", "-")
            add_provider_noninteractive(
                key=key,
                name=args.name,
                dashboard_url=args.dashboard_url,
                login_url=args.login_url,
                api_url=args.api_url,
                env_var=args.env_var,
            )
        else:
            providers = load_providers()
            add_custom_provider(providers)
        return
    
    # List
    if args.list:
        list_providers()
        return
    
    # Enable/Disable
    if args.enable:
        toggle_provider(args.enable, True)
        return
    if args.disable:
        toggle_provider(args.disable, False)
        return
    
    # Login
    if args.login:
        providers = load_providers()
        targets = list(providers.keys()) if args.login == "all" else args.login.split(",")
        for t in targets:
            t = t.strip()
            if t in providers:
                manual_login(t)
            else:
                print(f"⚠ Unknown: {t}  (available: {', '.join(providers.keys())})")
        return
    
    # Check
    global CACHE_TTL_SECONDS
    if args.no_cache:
        CACHE_TTL_SECONDS = 0
    
    providers = load_providers()
    enabled = get_enabled_providers()
    
    print("🔍 LLM Quota Check (Browser-First)")
    print(f"   Providers: {len(enabled)}/{len(providers)} enabled")
    print(f"   Profile: {BROWSER_PROFILE_DIR}")
    print(f"   Mode: {'API-only' if args.api_only else 'Browser + API fallback'}")
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    results = check_all(args.provider, args.api_only)
    
    # Merge with existing data (don't overwrite other providers)
    existing = load_cached_data()
    existing.update(results)
    save_quota_data(existing)
    
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    else:
        print(format_results(results))


if __name__ == "__main__":
    main()
