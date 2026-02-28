# LLM Quota Dashboard

Automated LLM usage/quota monitoring dashboard for OpenClaw. Checks quota limits for multiple LLM providers and displays them in a unified dashboard with alerts.

## 🎯 Features

- **Multi-Provider Support**: Z.AI, DashScope, Kimi, MiniMax, Anthropic
- **Auto-Checking**: Hourly quota checks via cron
- **Alerts**: Low quota warnings (<20% remaining)
- **Caching**: 1-hour TTL to avoid rate limits
- **Platform Support**: Terminal + WhatsApp formatting
- **Browser Automation**: Playwright-based scraping for providers without APIs

## 📊 Supported Providers

| Provider | Dashboard URL | API Available | Status |
|----------|--------------|---------------|--------|
| **Z.AI** | https://api.z.ai/dashboard | ✅ `/api/monitor/usage/quota/limit` | Working |
| **DashScope** | https://dashscope.console.aliyun.com/dashboard | ⚠️ Console only | Needs API key |
| **Kimi** | https://platform.moonshot.cn/dashboard/usage | ❌ Browser only | Working (screenshot) |
| **MiniMax** | https://platform.minimaxi.com/dashboard | ⚠️ Needs implementation | Pending |
| **Anthropic** | https://console.anthropic.com/settings/limits | ✅ Rate limit headers | Needs API key |

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd tasks/llm-quota-dashboard
pip3 install playwright requests --break-system-packages
playwright install webkit chromium
```

### 2. Set API Keys (Optional)

Set environment variables for providers you want to monitor:

```bash
export ZAI_API_KEY="your-zai-api-key"
export DASHSCOPE_API_KEY="your-dashscope-api-key"
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

### 3. Run Quota Check

```bash
# Full check with refresh
python3 scripts/check_quota.py

# Or use the plugin CLI
python3 scripts/llm_quota_plugin.py refresh
```

### 4. View Dashboard

```bash
# Terminal format
python3 scripts/dashboard_ui.py

# WhatsApp format
python3 scripts/dashboard_ui.py --platform whatsapp

# Compact summary
python3 scripts/dashboard_ui.py --summary
```

## 📖 CLI Commands

### Plugin CLI (`llm_quota_plugin.py`)

```bash
# Get current status
python3 scripts/llm_quota_plugin.py status

# Get status for specific provider
python3 scripts/llm_quota_plugin.py status --provider zai

# Force refresh (bypass cache)
python3 scripts/llm_quota_plugin.py refresh --force

# Check for low quota alerts
python3 scripts/llm_quota_plugin.py alerts

# Display summary
python3 scripts/llm_quota_plugin.py summary

# Output as JSON
python3 scripts/llm_quota_plugin.py status --json
```

### Dashboard UI (`dashboard_ui.py`)

```bash
# Full dashboard (terminal)
python3 scripts/dashboard_ui.py

# WhatsApp format
python3 scripts/dashboard_ui.py --platform whatsapp

# Compact summary only
python3 scripts/dashboard_ui.py --summary

# JSON output
python3 scripts/dashboard_ui.py --json
```

## 🏗️ Architecture

```
┌─────────────────┐
│  OpenClaw       │
│  Dashboard      │
│  [Usage Tab]    │
└─────────────────┘
         ↓ (Browser Tool)
┌─────────────────┐
│  Playwright     │
│  Automation     │
└─────────────────┘
         ↓
┌─────────────────┐
│  Provider       │
│  Dashboards     │
└─────────────────┘
```

## 📁 File Structure

```
tasks/llm-quota-dashboard/
├── TASK.md                  ← Task briefing
├── PROGRESS.md              ← Progress tracker
├── scripts/
│   ├── check_quota.py       ← Browser automation
│   ├── llm_quota_plugin.py  ← OpenClaw plugin
│   ├── dashboard_ui.py      ← Dashboard UI
│   └── setup_cron.py        ← Cron setup helper
├── data/
│   ├── quota_data.json      ← Cached quota data
│   └── schema.json          ← Data model schema
├── docs/
│   └── README.md            ← This file
└── output/
    └── screenshots/         ← Dashboard screenshots
```

## ⚙️ Configuration

### Cache Settings

- **TTL**: 1 hour (3600 seconds)
- **Location**: `data/quota_data.json`
- **Format**: JSON with UTF-8 encoding

### Alert Thresholds

- **Critical**: < 10% remaining (immediate alert)
- **Warning**: < 20% remaining (notify on next check)
- **Info**: < 50% remaining (log only)

### Cron Schedule

- **Hourly Check**: Every hour at minute 0 (Asia/Hong_Kong)
- **Alert Check**: Every 6 hours

## 🔧 API Endpoints

### Z.AI

- **Endpoint**: `https://api.z.ai/api/monitor/usage/quota/limit`
- **Auth**: Bearer token (`ZAI_API_KEY`)
- **Response**: Limits array with TIME_LIMIT (5h) + TOKENS_LIMIT (6h)

### DashScope

- **Endpoint**: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1/models`
- **Auth**: Bearer token (`DASHSCOPE_API_KEY`)
- **Note**: No direct quota API, console scraping needed

### Anthropic

- **Endpoint**: `https://api.anthropic.com/v1/messages`
- **Auth**: Bearer token (`ANTHROPIC_API_KEY`)
- **Rate Limits**: Via response headers (`x-ratelimit-remaining-*`)

## 🧪 Testing

### Run All Tests

```bash
# Test Z.AI API
python3 scripts/check_quota.py

# Test plugin CLI
python3 scripts/llm_quota_plugin.py status
python3 scripts/llm_quota_plugin.py alerts

# Test dashboard UI
python3 scripts/dashboard_ui.py
python3 scripts/dashboard_ui.py --platform whatsapp
```

### Verify Accuracy

1. Run manual check: `python3 scripts/llm_quota_plugin.py refresh --force`
2. Compare with provider dashboard
3. Check cache file: `cat data/quota_data.json`

### Error Handling

The system handles:
- Network errors (retries 3 times)
- Missing API keys (graceful degradation)
- Invalid responses (error status + message)
- Browser automation failures (screenshot fallback)

## 📝 Troubleshooting

### "Missing API key" Errors

Set the required environment variable:

```bash
export ZAI_API_KEY="your-key-here"
```

### Browser Automation Fails

1. Ensure Playwright is installed: `pip3 install playwright`
2. Install browsers: `playwright install webkit chromium`
3. Check for headless browser restrictions

### Cache Not Updating

Delete cache file and force refresh:

```bash
rm data/quota_data.json
python3 scripts/llm_quota_plugin.py refresh --force
```

### Low Quota Not Alerting

Check alert thresholds in `scripts/dashboard_ui.py`:
- Critical: < 10%
- Warning: < 20%

## 🔐 Security

- **API Keys**: Use environment variables only (never commit)
- **Cache File**: Contains usage data only (no sensitive info)
- **Screenshots**: Stored locally in `output/screenshots/`

## 📈 Future Improvements

- [ ] MiniMax browser automation
- [ ] DashScope console scraping
- [ ] Historical usage graphs
- [ ] Web dashboard UI
- [ ] Email/WhatsApp notifications
- [ ] Custom alert thresholds per provider
- [ ] Usage trend analysis

## 📄 License

Internal tool for OpenClaw workspace.

---

**Last Updated**: 2026-02-28  
**Version**: 1.0.0  
**Status**: Phase 1 Complete (Z.AI + Kimi working)
