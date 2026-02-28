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

#### 🔷 SiliconFlow

| Field | Value |
|---|---|
| **Dashboard** | `https://cloud.siliconflow.cn/account/ak` |
| **Login** | `cloud.siliconflow.cn/account/login` |
| **Data found** | API keys, balance/credits |
| **API fallback** | ❌ |

**Note**: Free tier for BAAI/bge-m3 embedding + reranker. Used for OpenClaw memory system.

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

## Using OpenClaw Browser (Alternative)

Instead of Playwright's separate browser profile, you can use the OpenClaw-managed Chrome browser which may already have your sessions logged in:

1. **OpenClaw browser profile**: `~/.openclaw/browser/openclaw/user-data`
2. **Playwright profile**: `~/.llm-quota-browser/`

These are **separate** browser profiles. To share sessions, you could:
- Copy cookies from OpenClaw profile to Playwright profile
- Or modify `check_quota.py` to use CDP connection to OpenClaw's Chrome

For now, the simplest approach: run `--login all` once per provider in the Playwright browser.

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
