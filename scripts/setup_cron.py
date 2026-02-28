#!/usr/bin/env python3
"""
Setup cron jobs for LLM Quota Dashboard auto-checks.
Creates hourly quota checks and low-quota alert notifications.
"""

import json
import sys
from pathlib import Path

# OpenClaw workspace
WORKSPACE = Path.home() / ".openclaw" / "workspace"
TASK_DIR = WORKSPACE / "tasks" / "llm-quota-dashboard"
SCRIPTS_DIR = TASK_DIR / "scripts"


def create_cron_job_config() -> dict:
    """Create cron job configuration for OpenClaw."""
    
    # Hourly quota check job
    hourly_check_job = {
        "name": "llm-quota-hourly-check",
        "schedule": {
            "kind": "cron",
            "expr": "0 * * * *",  # Every hour at minute 0
            "tz": "Asia/Hong_Kong"
        },
        "payload": {
            "kind": "systemEvent",
            "text": "🔍 Running hourly LLM quota check..."
        },
        "sessionTarget": "main",
        "enabled": True,
        "delivery": {
            "mode": "none"  # Silent run, results saved to file
        }
    }
    
    # Low quota alert check (every 6 hours)
    alert_check_job = {
        "name": "llm-quota-alert-check",
        "schedule": {
            "kind": "every",
            "everyMs": 21600000,  # 6 hours in milliseconds
        },
        "payload": {
            "kind": "systemEvent",
            "text": "⚠️ Checking LLM quota alerts... Please run: python3 tasks/llm-quota-dashboard/scripts/llm_quota_plugin.py alerts"
        },
        "sessionTarget": "main",
        "enabled": True,
        "delivery": {
            "mode": "announce"
        }
    }
    
    return {
        "hourly_check": hourly_check_job,
        "alert_check": alert_check_job
    }


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Setup LLM Quota cron jobs")
    parser.add_argument("--show", action="store_true", help="Show job config without installing")
    parser.add_argument("--remove", action="store_true", help="Remove existing cron jobs")
    args = parser.parse_args()
    
    config = create_cron_job_config()
    
    if args.show:
        print(json.dumps(config, indent=2, ensure_ascii=False))
        return
    
    print("📅 LLM Quota Dashboard - Cron Job Setup")
    print("=" * 50)
    print("\nThis script will create the following cron jobs:")
    print("\n1. Hourly Quota Check")
    print("   - Schedule: Every hour at minute 0 (Asia/Hong_Kong)")
    print("   - Action: Run quota check and save to cache")
    print("   - Notification: Silent (results saved to file)")
    print("\n2. Low Quota Alert Check")
    print("   - Schedule: Every 6 hours")
    print("   - Action: Check for quotas < 20%")
    print("   - Notification: Announce if alerts found")
    print("\n" + "=" * 50)
    print("\nTo install these jobs manually, use:")
    print("  openclaw cron add --job '<json_config>'")
    print("\nOr use the OpenClaw gateway config to add them.")
    print("\n💡 Tip: You can also run checks manually with:")
    print(f"   python3 {SCRIPTS_DIR}/llm_quota_plugin.py refresh")
    print(f"   python3 {SCRIPTS_DIR}/llm_quota_plugin.py alerts")


if __name__ == "__main__":
    main()
