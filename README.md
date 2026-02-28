# LLM Quota Dashboard

Neumorphic dashboard for tracking LLM provider quotas and billing — browser-scrape first, API fallback.

📊 **Live**: [quota.joe2643.xyz](https://quota.joe2643.xyz) / `localhost:8501`

---

## Quick Start

```bash
cd tasks/llm-quota-dashboard

# 1. Start the dashboard
python3 web/server.py        # http://localhost:8501

# 2. First time: login to providers
python3 scripts/check_quota.py --login all

# 3. Check all quotas
python3 scripts/check_quota.py --no-cache
```

## Architecture

```
Browser-First Design:
  OpenClaw Browser (Chrome profile) → navigate dashboard → screenshot + extract
  ↓ (fallback if no browser)
  API check (where available)
  ↓
  data/quota_data.json → Flask server → Neumorphic UI
```

### Files

```
web/
  index.html          # Neumorphic frontend (vanilla HTML/CSS/JS)
  server.py           # Flask backend (port 8501)
scripts/
  check_quota.py      # Browser scraper + API checker
data/
  providers.json      # Provider configs (editable)
  quota_data.json     # Latest quota data (auto-generated)
output/screenshots/   # Dashboard screenshots
```

---

## Provider Setup Guide

### How It Works

The checker uses a **Playwright persistent browser profile** (`~/.llm-quota-browser/`) to visit each provider's dashboard page. Cookies are saved, so you only need to login once per provider.

> **Alternatively**: You can use the OpenClaw managed browser (Chrome profile at `~/.openclaw/browser/openclaw/user-data`) which may already have your sessions logged in. See "Using OpenClaw Browser" below.

### Step-by-Step Login Process

For each provider, the `--login` command opens a headed Chromium browser:

```bash
python3 scripts/check_quota.py --login <provider>
```

1. A browser window opens on your machine
2. Navigate to the login page (auto-opened)
3. Log in with your credentials
4. **Close the browser window** (not just the tab)
5. Script reports success/failure, cookies saved

### Provider Details

#### 🔵 Z.AI

| Field | Value |
|---|---|
| **Dashboard** | `https://z.ai/manage-apikey/rate-limits` |
| **Billing** | `https://z.ai/manage-apikey/billing` |
| **Login** | Email + password at `z.ai/manage-apikey/rate-limits` (redirects to auth) |
| **Data found** | Rate limits table (model × concurrency), Balance ($), Cash/Credits split |
| **API fallback** | ✅ `api.z.ai/api/monitor/usage/quota/limit` (5h window quota %) |
| **Env var** | `ZAI_API_KEY` |

**Login steps**:
1. Opens Z.AI rate limits page → redirects to `chat.z.ai/auth`
2. Enter email + password (or use "快捷登录" social login)
3. After login, auto-redirects back to rate limits page
4. Close browser

**What's scraped**: Concurrency table, balance amount, cash vs credits breakdown.

---

#### 🟠 DashScope (Alibaba Cloud)

| Field | Value |
|---|---|
| **Dashboard** | `https://usercenter2-intl.aliyun.com/` |
| **Model Studio** | `https://modelstudio.console.alibabacloud.com/ap-southeast-1/` |
| **Login** | Alibaba Cloud account (Google/email) |
| **Data found** | Spending overview chart, monthly payment amount, payment method |
| **API fallback** | ✅ Key validation only |
| **Env var** | `DASHSCOPE_API_KEY` |

**Login steps**:
1. Opens Alibaba Cloud billing center
2. If not logged in → redirects to `account.alibabacloud.com` login
3. Login with Alibaba Cloud account (Google, email, or Aliyun ID)
4. After login, see "Account Overview" with spending chart
5. Close browser

**Note**: Account is on international site (ap-southeast-1). The Chinese `bailian.console.aliyun.com` redirects here. Banner says "您当前使用的账号归属国际站".

---

#### 🟤 Anthropic

| Field | Value |
|---|---|
| **Dashboard** | `https://platform.claude.com/settings/limits` |
| **Usage** | `https://platform.claude.com/settings/usage` |
| **Login** | Google or email at `platform.claude.com/login` |
| **Data found** | Rate limits (RPM/TPM per model), usage/spend |
| **API fallback** | ❌ |

**Login steps**:
1. Opens `platform.claude.com/login`
2. Click "Continue with Google" or enter email
3. After login, see rate limits table
4. Close browser

**Note**: URL changed from `console.anthropic.com` to `platform.claude.com` (2025+).

---

#### 🟣 Kimi (Moonshot)

| Field | Value |
|---|---|
| **Dashboard** | `https://platform.moonshot.cn/console/account` |
| **Login** | Phone number or email |
| **Data found** | Balance, usage stats |
| **API fallback** | ❌ |

**Login steps**:
1. Opens Moonshot platform
2. Login with phone number or email
3. See account page with balance
4. Close browser

**Note**: Page loads slowly — may timeout on first attempt. Retry if needed.

---

#### 🟢 MiniMax

| Field | Value |
|---|---|
| **Dashboard** | `https://platform.minimaxi.com/user-center/basic-information/interface-key` |
| **Login** | `platform.minimaxi.com/login` |
| **Data found** | API keys, balance info |
| **API fallback** | ❌ |

---

## Adding New Providers

### Interactive Setup
```bash
python3 scripts/check_quota.py --setup
```
Shows available templates and lets you pick. Templates include: OpenAI, Google Gemini, DeepSeek, Groq, Together AI, Fireworks, Mistral, Cohere.

### Non-Interactive (Agent Use)
```bash
# From template
python3 scripts/check_quota.py --add --key deepseek

# Custom URL
python3 scripts/check_quota.py --add \
  --key openrouter \
  --name "OpenRouter" \
  --dashboard-url "https://openrouter.ai/settings/credits"
```

### Direct Edit
Edit `data/providers.json`:
```json
{
  "my_provider": {
    "name": "My Provider",
    "dashboard_url": "https://example.com/dashboard",
    "login_url": "https://example.com/login",
    "extra_pages": ["https://example.com/billing"],
    "api_url": "https://api.example.com/quota",
    "env_var": "MY_PROVIDER_API_KEY",
    "color": "🔹",
    "enabled": true,
    "notes": "Any notes"
  }
}
```

**Required**: `name`, `dashboard_url`
**Optional**: everything else

---

## CLI Reference

```bash
# Check
python3 scripts/check_quota.py                  # All enabled providers
python3 scripts/check_quota.py --provider zai    # Specific provider(s)
python3 scripts/check_quota.py --api-only        # API only (no browser)
python3 scripts/check_quota.py --no-cache        # Skip 1h cache
python3 scripts/check_quota.py --json            # JSON output

# Manage providers
python3 scripts/check_quota.py --setup           # Interactive setup
python3 scripts/check_quota.py --add             # Add provider
python3 scripts/check_quota.py --list            # List all providers
python3 scripts/check_quota.py --enable <key>    # Enable provider
python3 scripts/check_quota.py --disable <key>   # Disable provider

# Login
python3 scripts/check_quota.py --login <key>     # Login single provider
python3 scripts/check_quota.py --login all       # Login all providers
```

---

## CDP Scraper (Recommended)

The **primary scraper** (`scripts/scrape_dashboards.py`) connects directly to Chrome via CDP (Chrome DevTools Protocol) — no Playwright needed. This is faster, lighter, and reuses your existing logged-in sessions.

### How It Works

1. Connects to Chrome's CDP WebSocket (port 18800)
2. Attaches to a single existing tab
3. Navigates to each provider sequentially (same tab)
4. Waits for data keywords to appear (polling, not blind timeout)
5. Extracts page text via `Runtime.evaluate`
6. Parses with provider-specific regex
7. Returns to `about:blank` when done

### Key Technical Details

- **WebSocket origin bypass**: Chrome blocks WS connections by default. Use `suppress_origin=True` in websocket-client
- **Browser-level WS + Target.attachToTarget**: Connect to browser WS (from `/json/version`), not per-tab WS (which gets 403)
- **Z.AI**: Navigate to subscription → poll-click `[role=tab]:text("Usage")` → wait for "Hours Quota"
- **DashScope popover**: CDP `Input.dispatchMouseEvent` (`mouseMoved`) on the data cell (TD, not TH header) triggers Ant Design Popover. Must move mouse away first (0,0) then to target
- **Kimi**: Shows `-` instead of `%` when quota just reset → treat as 0% used
- **Wait-for-data pattern**: Each provider defines keywords to poll for. Script waits until keywords appear in `document.body.innerText`, with per-provider timeout

### Setup for New Agent

```bash
# Prerequisites
pip install websocket-client

# Ensure OpenClaw browser is running with CDP
openclaw browser start  # or check status

# Verify CDP is accessible
curl -s http://127.0.0.1:18800/json/version | python3 -c "import json,sys; print(json.load(sys.stdin)['webSocketDebuggerUrl'])"

# Run scraper
python3 scripts/scrape_dashboards.py           # All 5 providers
python3 scripts/scrape_dashboards.py -p zai     # Single provider
python3 scripts/scrape_dashboards.py --debug    # Show extracted text
python3 scripts/scrape_dashboards.py --json     # JSON output

# Results saved to data/quota_data.json
```

### Adding a New Provider to the Scraper

1. Add a `scrape_<name>(cdp: CDPSession)` function
2. Navigate to the dashboard URL
3. Wait for data keywords: `cdp.wait_for_text(["keyword1", "keyword2"], timeout=15)`
4. Extract text: `text = cdp.get_text()`
5. Parse with regex
6. Register in `PROVIDERS` dict
7. Add format logic in `format_provider()`

### Common Issues

| Issue | Solution |
|---|---|
| 403 on WebSocket | Use `suppress_origin=True` when connecting |
| Empty text / timeout | Provider not logged in — login via OpenClaw browser |
| Popover not mounting | Use CDP `Input.dispatchMouseEvent` on data cell, not header |
| Same-URL navigation doesn't reload | CDP `Page.navigate` to same URL is a no-op; script uses `Page.reload` |
| `content` empty from Z.AI | glm-5 has thinking mode enabled by default; pass `thinking: {type: "disabled"}` |

## Playwright Browser (Legacy/Fallback)

The legacy scraper (`scripts/check_quota.py`) uses Playwright with a separate browser profile at `~/.llm-quota-browser/`. Login once per provider with `--login <key>`. This approach is heavier and requires separate login sessions.

---

## Dashboard UI

**Design**: Neumorphism (Soft UI)
- Background: `#E0E5EC` (cool grey)
- Shadows: Dual opposing (light top-left, dark bottom-right)
- Fonts: Plus Jakarta Sans (headings) + DM Sans (body)
- Cards with inset-deep emoji wells, quota bars, screenshot previews
- Responsive: works on mobile

**Stack**: Flask + vanilla HTML/CSS/JS (no build step, no npm)

---

## Deployment

Already configured via Cloudflare Tunnel:
```yaml
# ~/.cloudflared/config.yml
- hostname: quota.joe2643.xyz
  service: http://localhost:8501
```

Start server:
```bash
nohup python3 web/server.py > flask.log 2>&1 &
```
