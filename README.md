# LLM Quota Dashboard

Neumorphic dashboard for tracking LLM provider quotas and billing — browser-scrape first, API fallback.

📊 **Demo**: [GitHub Pages](https://joe2643.github.io/llm-quota-dashboard/) (static sample data)

![Dashboard Preview](docs/preview.png)

---

## Quick Start

```bash
# Clone
git clone https://github.com/<your-user>/llm-quota-dashboard.git
cd llm-quota-dashboard

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
  Chrome (existing profile) → navigate dashboard → extract text via CDP
  ↓ (fallback if no browser)
  API check (where available)
  ↓
  data/quota_data.json → Flask server → Neumorphic UI
```

### Files

```
index.html              # GitHub Pages entry (static demo)
web/
  index.html            # Neumorphic frontend (vanilla HTML/CSS/JS)
  server.py             # Flask backend (port 8501)
scripts/
  scrape_dashboards.py  # CDP direct scraper (primary, recommended)
  check_quota.py        # Playwright browser scraper (legacy/fallback)
data/
  providers.json        # Provider configs (editable)
  quota_data.json       # Latest quota data (auto-generated)
  schema.json           # Data schema reference
```

---

## Provider Setup Guide

### How It Works

The CDP scraper connects to an existing Chrome instance via DevTools Protocol, navigates to each provider's dashboard, and extracts quota data from the page text. Since it reuses your existing browser sessions, there's **no separate login step** — just be logged in to your providers in Chrome.

The legacy Playwright scraper uses a separate browser profile (`~/.llm-quota-browser/`). Login once per provider with `--login <key>`.

### Supported Providers

| Provider | Dashboard URL | Data Extracted | API Fallback |
|---|---|---|---|
| **Z.AI** | `z.ai/manage-apikey/subscription` | Rate limits, Balance, Cash/Credits | ✅ quota % |
| **DashScope** | `modelstudio.console.alibabacloud.com` | 5h/Weekly/Monthly quotas (via popover) | ✅ key validation |
| **Anthropic** | `platform.claude.com/settings/usage` | RPM/TPM limits, usage/spend | ❌ |
| **Kimi** | `platform.moonshot.cn/console/account` | Balance, usage stats | ❌ |
| **MiniMax** | `platform.minimaxi.com/user-center` | Balance, free quota, usage | ❌ |

### Adding New Providers

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

Or use the CLI:
```bash
python3 scripts/check_quota.py --setup           # Interactive
python3 scripts/check_quota.py --add --key deepseek --name "DeepSeek" --dashboard-url "https://platform.deepseek.com/usage"
```

Templates included: OpenAI, Google Gemini, DeepSeek, Groq, Together AI, Fireworks, Mistral, Cohere.

---

## CDP Scraper (Recommended)

The primary scraper (`scripts/scrape_dashboards.py`) connects directly to Chrome via CDP — no Playwright needed.

### Prerequisites

```bash
pip install websocket-client

# Chrome must be running with remote debugging enabled
# OpenClaw users: openclaw browser start
# Manual: chrome --remote-debugging-port=18800
```

### Usage

```bash
python3 scripts/scrape_dashboards.py              # All providers
python3 scripts/scrape_dashboards.py -p zai        # Single provider
python3 scripts/scrape_dashboards.py --debug       # Show extracted text
python3 scripts/scrape_dashboards.py --json        # JSON output
```

### How It Works

1. Gets browser WebSocket URL from `http://127.0.0.1:18800/json/version`
2. Connects with `suppress_origin=True` (bypasses Chrome's WS origin check)
3. Uses `Target.attachToTarget` to control a single tab
4. Navigates to each provider sequentially
5. Polls for data keywords before extracting (no blind timeouts)
6. Parses page text with provider-specific regex
7. Saves results to `data/quota_data.json`

### Key Technical Details

- **WebSocket origin bypass**: Chrome blocks WS connections by default → `suppress_origin=True`
- **Browser-level WS**: Connect to browser endpoint, not per-tab (avoids 403)
- **CDP mouse hover for popovers**: `Input.dispatchMouseEvent` on data cells triggers Ant Design Popovers (e.g., DashScope). Must move mouse away first (0,0) then to target
- **Wait-for-data pattern**: Each provider defines keywords to poll for. Scraper waits until keywords appear in `document.body.innerText`

### Adding a Provider to the Scraper

1. Add a `scrape_<name>(cdp)` function
2. Navigate: `cdp.navigate(url)`
3. Wait for data: `cdp.wait_for_text(["keyword1", "keyword2"], timeout=15)`
4. Extract: `text = cdp.get_text()`
5. Parse with regex
6. Register in `PROVIDERS` dict

### Troubleshooting

| Issue | Solution |
|---|---|
| 403 on WebSocket | Use `suppress_origin=True` when connecting |
| Empty text / timeout | Provider not logged in — login in Chrome first |
| Popover not appearing | Use CDP `Input.dispatchMouseEvent` on data cell, not header |
| Navigation doesn't reload | Same-URL navigate is no-op; use `Page.reload` |

---

## CLI Reference

```bash
# Check quotas
python3 scripts/check_quota.py                    # All enabled providers
python3 scripts/check_quota.py --provider zai      # Specific provider(s)
python3 scripts/check_quota.py --api-only          # API only (no browser)
python3 scripts/check_quota.py --no-cache          # Skip 1h cache
python3 scripts/check_quota.py --json              # JSON output

# Manage providers
python3 scripts/check_quota.py --setup             # Interactive setup
python3 scripts/check_quota.py --add               # Add provider
python3 scripts/check_quota.py --list              # List all providers

# Login (Playwright legacy)
python3 scripts/check_quota.py --login <key>       # Login single provider
python3 scripts/check_quota.py --login all         # Login all providers
```

---

## Dashboard UI

**Design**: Neumorphism (Soft UI)
- Background: `#E0E5EC` (cool grey)
- Shadows: Dual opposing (light top-left, dark bottom-right)
- Fonts: Plus Jakarta Sans + DM Sans
- Cards with inset emoji wells, quota bars, responsive layout

**Stack**: Flask + vanilla HTML/CSS/JS (no build step, no npm)

The frontend supports two modes:
- **With Flask**: Fetches from `/api/providers` and `/api/data`
- **Static (GitHub Pages)**: Falls back to `data/providers.json` and `data/quota_data.json`

---

## Deployment

### Local
```bash
python3 web/server.py    # http://localhost:8501
```

### GitHub Pages (Static Demo)
The repo includes `index.html` at root with static JSON fallback. Enable GitHub Pages in repo settings (source: `master`, root `/`).

### With Reverse Proxy (Cloudflare Tunnel, nginx, etc.)
```yaml
# Example: Cloudflare Tunnel
- hostname: quota.yourdomain.com
  service: http://localhost:8501
```

---

## License

MIT
