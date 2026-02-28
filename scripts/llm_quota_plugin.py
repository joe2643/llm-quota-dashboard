#!/usr/bin/env python3
"""
LLM Quota Plugin for OpenClaw
Integrates quota checking with OpenClaw dashboard and cron-based auto-checks.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import requests

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from check_quota import (
    check_all_quotas,
    load_cached_data,
    save_quota_data,
    format_quota_summary,
    is_cache_valid,
    QUOTA_FILE,
    CACHE_TTL_SECONDS,
    PROVIDERS,
)

# OpenClaw workspace
WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE", Path.home() / ".openclaw" / "workspace"))
TASK_DIR = WORKSPACE / "tasks" / "llm-quota-dashboard"
DATA_DIR = TASK_DIR / "data"
OUTPUT_DIR = TASK_DIR / "output"


def get_quota_status(provider: Optional[str] = None) -> dict:
    """
    Get current quota status.
    
    Args:
        provider: Optional provider key (zai, dashscope, kimi, minimax, anthropic)
    
    Returns:
        dict: Quota data for specified provider or all providers
    """
    cached_data = load_cached_data()
    
    if provider:
        if provider not in PROVIDERS:
            return {"error": f"Unknown provider: {provider}"}
        
        if provider in cached_data:
            return cached_data[provider]
        return {"error": "No data available", "status": "error"}
    
    return cached_data


def refresh_quota(force: bool = False) -> dict:
    """
    Refresh quota data from providers.
    
    Args:
        force: If True, bypass cache and fetch fresh data
    
    Returns:
        dict: Fresh quota data
    """
    if force:
        # Clear cache
        if QUOTA_FILE.exists():
            QUOTA_FILE.unlink()
    
    # Run quota check
    results = asyncio.run(check_all_quotas())
    return results


def check_low_quota_alerts() -> list:
    """
    Check for low quota alerts (<20% remaining).
    
    Returns:
        list: List of providers with low quota
    """
    alerts = []
    cached_data = load_cached_data()
    
    for provider_key, data in cached_data.items():
        if data.get("status") != "success":
            continue
        
        quota_percent = data.get("quota_percent")
        if quota_percent is not None and quota_percent < 20:
            alerts.append({
                "provider": PROVIDERS[provider_key]["name"],
                "provider_key": provider_key,
                "quota_percent": quota_percent,
                "severity": "critical" if quota_percent < 10 else "warning",
                "reset_at": data.get("reset_at"),
            })
    
    return alerts


def format_alert_message(alerts: list) -> str:
    """Format alerts as human-readable message."""
    if not alerts:
        return "✅ All LLM quotas are healthy (>20% remaining)"
    
    lines = ["⚠️ LLM Quota Alerts", "=" * 40]
    for alert in alerts:
        icon = "🔴" if alert["severity"] == "critical" else "🟡"
        reset_time = ""
        if alert.get("reset_at"):
            try:
                reset_dt = datetime.fromisoformat(alert["reset_at"].replace("Z", "+00:00"))
                reset_time = f" (resets: {reset_dt.strftime('%m-%d %H:%M')})"
            except:
                pass
        
        lines.append(f"{icon} {alert['provider']}: {alert['quota_percent']:.0f}% remaining{reset_time}")
    
    lines.append("")
    lines.append("Run quota check for details.")
    return "\n".join(lines)


def api_handler(action: str, **kwargs) -> dict:
    """
    Handle API requests for quota dashboard.
    
    Actions:
    - get_status: Get current quota status
    - refresh: Force refresh quota data
    - check_alerts: Check for low quota alerts
    - get_history: Get quota history (not yet implemented)
    
    Args:
        action: API action to perform
        **kwargs: Additional parameters
    
    Returns:
        dict: API response
    """
    if action == "get_status":
        provider = kwargs.get("provider")
        return {"success": True, "data": get_quota_status(provider)}
    
    elif action == "refresh":
        force = kwargs.get("force", False)
        results = refresh_quota(force)
        return {"success": True, "data": results, "message": "Quota data refreshed"}
    
    elif action == "check_alerts":
        alerts = check_low_quota_alerts()
        return {
            "success": True,
            "data": alerts,
            "message": format_alert_message(alerts),
            "has_alerts": len(alerts) > 0,
        }
    
    elif action == "get_summary":
        cached_data = load_cached_data()
        summary = format_quota_summary(cached_data)
        return {"success": True, "data": summary}
    
    else:
        return {"success": False, "error": f"Unknown action: {action}"}


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="LLM Quota Plugin for OpenClaw")
    parser.add_argument("action", choices=["status", "refresh", "alerts", "summary"],
                       help="Action to perform")
    parser.add_argument("--provider", "-p", choices=list(PROVIDERS.keys()),
                       help="Specific provider to check")
    parser.add_argument("--force", "-f", action="store_true",
                       help="Force refresh (bypass cache)")
    parser.add_argument("--json", "-j", action="store_true",
                       help="Output as JSON")
    
    args = parser.parse_args()
    
    if args.action == "status":
        result = api_handler("get_status", provider=args.provider)
    elif args.action == "refresh":
        result = api_handler("refresh", force=args.force)
    elif args.action == "alerts":
        result = api_handler("check_alerts")
    elif args.action == "summary":
        result = api_handler("get_summary")
    else:
        print(f"Unknown action: {args.action}")
        sys.exit(1)
    
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if "message" in result:
            print(result["message"])
        elif "data" in result and isinstance(result["data"], str):
            print(result["data"])
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
