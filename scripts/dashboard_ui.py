#!/usr/bin/env python3
"""
LLM Quota Dashboard UI
Text-based dashboard with progress bars, alerts, and multi-provider display.
Optimized for terminal and WhatsApp messaging.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Configuration
WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE", Path.home() / ".openclaw" / "workspace"))
TASK_DIR = WORKSPACE / "tasks" / "llm-quota-dashboard"
DATA_DIR = TASK_DIR / "data"
QUOTA_FILE = DATA_DIR / "quota_data.json"

PROVIDERS = {
    "zai": {"name": "Z.AI", "color": "🔵"},
    "dashscope": {"name": "DashScope", "color": "🟠"},
    "kimi": {"name": "Kimi", "color": "🟣"},
    "minimax": {"name": "MiniMax", "color": "🟢"},
    "anthropic": {"name": "Anthropic", "color": "🟤"},
}


def load_quota_data() -> dict:
    """Load quota data from cache file."""
    if QUOTA_FILE.exists():
        try:
            with open(QUOTA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def create_progress_bar(percent: float, width: int = 20, filled_char: str = "█", empty_char: str = "░") -> str:
    """Create a text-based progress bar."""
    if percent is None:
        return "?" * width
    
    percent = max(0, min(100, percent))  # Clamp to 0-100
    filled = int(width * percent / 100)
    empty = width - filled
    return filled_char * filled + empty_char * empty


def get_quota_status_icon(status: str) -> str:
    """Get status icon."""
    icons = {
        "success": "✅",
        "error": "❌",
        "api_accessible": "✓",
        "cached": "💾",
    }
    return icons.get(status, "❓")


def get_alert_severity(percent: Optional[float]) -> str:
    """Determine alert severity based on quota percentage."""
    if percent is None:
        return "info"
    if percent < 10:
        return "critical"
    if percent < 20:
        return "warning"
    if percent < 50:
        return "info"
    return "ok"


def format_reset_time(reset_at: Optional[str]) -> str:
    """Format reset timestamp as human-readable string."""
    if not reset_at:
        return ""
    
    try:
        reset_dt = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = reset_dt - now
        
        if delta.total_seconds() < 0:
            return "(reset overdue)"
        
        hours = int(delta.total_seconds() / 3600)
        minutes = int((delta.total_seconds() % 3600) / 60)
        
        if hours > 24:
            return f"(resets: {reset_dt.strftime('%m-%d %H:%M')})"
        elif hours > 0:
            return f"(resets in {hours}h {minutes}m)"
        else:
            return f"(resets in {minutes}m)"
    except:
        return ""


def render_dashboard(data: dict, platform: str = "terminal") -> str:
    """
    Render quota dashboard as text.
    
    Args:
        data: Quota data dict
        platform: 'terminal' or 'whatsapp' (affects formatting)
    
    Returns:
        str: Formatted dashboard text
    """
    lines = []
    
    # Header
    if platform == "terminal":
        lines.append("╔" + "═" * 48 + "╗")
        lines.append("║" + " " * 12 + "📊 LLM Quota Dashboard" + " " * 12 + "║")
        lines.append("╚" + "═" * 48 + "╝")
    else:
        lines.append("*📊 LLM Quota Dashboard*")
        lines.append("=" * 40)
    
    lines.append("")
    
    # Provider rows
    alerts = []
    
    for provider_key, config in PROVIDERS.items():
        provider_data = data.get(provider_key, {})
        status = provider_data.get("status", "error")
        name = config["name"]
        icon = config["color"]
        
        if status == "success":
            quota_percent = provider_data.get("quota_percent")
            usage_percent = provider_data.get("usage_percent")
            
            if quota_percent is not None:
                bar = create_progress_bar(quota_percent, width=20)
                severity = get_alert_severity(quota_percent)
                
                # Add alert marker
                alert_marker = ""
                if severity == "critical":
                    alert_marker = " 🔴 CRITICAL"
                    alerts.append(f"{name}: {quota_percent:.0f}% remaining")
                elif severity == "warning":
                    alert_marker = " 🟡 LOW"
                    alerts.append(f"{name}: {quota_percent:.0f}% remaining")
                
                reset_info = format_reset_time(provider_data.get("reset_at"))
                
                if platform == "terminal":
                    lines.append(f"{icon} {name:12} [{bar}] {quota_percent:5.0f}%{alert_marker}")
                    if reset_info:
                        lines.append(f"{' ' * 18}  {reset_info}")
                else:
                    lines.append(f"*{name}*: {quota_percent:.0f}% [{bar}]{alert_marker}")
                    if reset_info:
                        lines.append(f"  _{reset_info}_")
            else:
                lines.append(f"{icon} {name:12} ✓ API accessible")
        
        elif status == "api_accessible":
            lines.append(f"{icon} {name:12} ✓ API accessible")
        
        else:
            error_msg = provider_data.get("message", "Unknown error")
            if platform == "terminal":
                lines.append(f"{icon} {name:12} ❌ {error_msg[:30]}")
            else:
                lines.append(f"{icon} *{name}*: ❌ {error_msg[:30]}")
    
    lines.append("")
    
    # Alerts section
    if alerts:
        if platform == "terminal":
            lines.append("╔" + "═" * 48 + "╗")
            lines.append("║" + " " * 5 + "⚠️  QUOTA ALERTS" + " " * 27 + "║")
            lines.append("╚" + "═" * 48 + "╝")
        else:
            lines.append("*⚠️ QUOTA ALERTS*")
            lines.append("-" * 40)
        
        for alert in alerts:
            lines.append(f"  • {alert}")
        lines.append("")
    
    # Footer
    last_check = None
    for provider_data in data.values():
        if provider_data.get("last_checked"):
            try:
                check_time = datetime.fromisoformat(provider_data["last_checked"].replace("Z", "+00:00"))
                if last_check is None or check_time > last_check:
                    last_check = check_time
            except:
                pass
    
    if last_check:
        time_str = last_check.strftime("%Y-%m-%d %H:%M:%S %Z")
    else:
        time_str = "Never"
    
    if platform == "terminal":
        lines.append("─" * 50)
        lines.append(f"Last updated: {time_str}")
        lines.append("Refresh: python3 scripts/llm_quota_plugin.py refresh")
    else:
        lines.append("-" * 40)
        lines.append(f"_Last updated: {time_str}_")
    
    return "\n".join(lines)


def render_summary(data: dict, platform: str = "terminal") -> str:
    """Render a compact summary (single message)."""
    total_providers = len(PROVIDERS)
    successful = sum(1 for k in PROVIDERS if data.get(k, {}).get("status") in ["success", "api_accessible"])
    alerts = sum(1 for k in PROVIDERS if data.get(k, {}).get("quota_percent", 100) < 20)
    
    if platform == "terminal":
        return f"📊 LLM Quota Summary: {successful}/{total_providers} providers checked, {alerts} alerts"
    else:
        status = "⚠️" if alerts > 0 else "✅"
        return f"{status} *LLM Quota*: {successful}/{total_providers} OK, {alerts} alerts"


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="LLM Quota Dashboard UI")
    parser.add_argument("--platform", "-p", choices=["terminal", "whatsapp"], default="terminal",
                       help="Output platform (affects formatting)")
    parser.add_argument("--summary", "-s", action="store_true",
                       help="Show compact summary only")
    parser.add_argument("--json", "-j", action="store_true",
                       help="Output as JSON")
    args = parser.parse_args()
    
    data = load_quota_data()
    
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif args.summary:
        print(render_summary(data, platform=args.platform))
    else:
        print(render_dashboard(data, platform=args.platform))


if __name__ == "__main__":
    main()
