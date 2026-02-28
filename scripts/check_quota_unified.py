"""
LLM Quota Check - Unified format for all providers
Support both 5h window and weekly quota (for Coding Plan)
"""
import requests
import os
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Output file
OUTPUT_FILE = Path(__file__).parent / "data" / "quota_data.json"

def check_zai_quota():
    """Check Z.AI quota - supports both 5h window and weekly."""
    try:
        api_key = os.getenv("ZAI_API_KEY")
        if not api_key:
            return {
                "5h_window": {"quota_percent": 0, "usage_percent": 100, "reset_at": "N/A", "status": "error"},
                "weekly": {"quota_percent": 0, "usage_percent": 0, "reset_at": "N/A", "status": "error"},
                "error": "Missing API key (ZAI_API_KEY)"
            }
        
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get("https://api.z.ai/api/v1/usage/quota", headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Support both new and old API format
            if "5h_window" in data:
                return {
                    "5h_window": data["5h_window"],
                    "weekly": data.get("weekly", {"quota_percent": 0, "usage_percent": 0, "reset_at": "N/A"}),
                    "status": "success"
                }
            else:
                # Old format - treat as 5h window
                return {
                    "5h_window": {
                        "quota_percent": data.get("quota_percent", 0),
                        "usage_percent": data.get("usage_percent", 100),
                        "reset_at": data.get("reset_at", "N/A"),
                        "status": "success"
                    },
                    "weekly": {
                        "quota_percent": data.get("weekly_quota_percent", 0),
                        "usage_percent": data.get("weekly_usage_percent", 0),
                        "reset_at": data.get("weekly_reset_at", "N/A"),
                        "status": "success"
                    },
                    "status": "success"
                }
        else:
            return {
                "5h_window": {"quota_percent": 0, "usage_percent": 100, "reset_at": "N/A", "status": "error"},
                "weekly": {"quota_percent": 0, "usage_percent": 0, "reset_at": "N/A", "status": "error"},
                "error": f"API error: {response.status_code}"
            }
    except Exception as e:
        return {
            "5h_window": {"quota_percent": 0, "usage_percent": 100, "reset_at": "N/A", "status": "error"},
            "weekly": {"quota_percent": 0, "usage_percent": 0, "reset_at": "N/A", "status": "error"},
            "error": str(e)
        }

def check_minimax_quota():
    """Check MiniMax quota - Coding Plan format."""
    try:
        api_key = os.getenv("MINIMAX_API_KEY")
        if not api_key:
            return {
                "5h_window": {"quota_percent": 0, "usage_percent": 100, "reset_at": "N/A", "status": "error"},
                "weekly": {"quota_percent": 0, "usage_percent": 0, "reset_at": "N/A", "status": "error"},
                "error": "Missing API key (MINIMAX_API_KEY)"
            }
        
        # MiniMax quota API (adjust endpoint as needed)
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get("https://api.minimaxi.com/v1/usage/quota", headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "5h_window": {
                    "quota_percent": data.get("5h_quota_percent", 0),
                    "usage_percent": data.get("5h_usage_percent", 100),
                    "reset_at": data.get("5h_reset_at", "N/A"),
                    "status": "success"
                },
                "weekly": {
                    "quota_percent": data.get("weekly_quota_percent", 0),
                    "usage_percent": data.get("weekly_usage_percent", 0),
                    "reset_at": data.get("weekly_reset_at", "N/A"),
                    "status": "success"
                },
                "status": "success"
            }
        else:
            return {
                "5h_window": {"quota_percent": 0, "usage_percent": 100, "reset_at": "N/A", "status": "error"},
                "weekly": {"quota_percent": 0, "usage_percent": 0, "reset_at": "N/A", "status": "error"},
                "error": f"API error: {response.status_code}"
            }
    except Exception as e:
        return {
            "5h_window": {"quota_percent": 0, "usage_percent": 100, "reset_at": "N/A", "status": "error"},
            "weekly": {"quota_percent": 0, "usage_percent": 0, "reset_at": "N/A", "status": "error"},
            "error": str(e)
        }

def check_dashscope_quota():
    """Check DashScope quota - balance based."""
    try:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            return {
                "5h_window": {"quota_percent": 0, "usage_percent": 100, "reset_at": "N/A", "status": "error"},
                "weekly": {"quota_percent": 0, "usage_percent": 0, "reset_at": "N/A", "status": "error"},
                "error": "Missing API key (DASHSCOPE_API_KEY)"
            }
        
        # DashScope uses balance, simulate quota format
        return {
            "5h_window": {
                "quota_percent": 0,
                "usage_percent": 0,
                "reset_at": "N/A",
                "status": "success",
                "note": "Balance-based billing"
            },
            "weekly": {
                "quota_percent": 0,
                "usage_percent": 0,
                "reset_at": "N/A",
                "status": "success",
                "note": "Balance-based billing"
            },
            "dashboard_url": "https://dashscope.console.aliyun.com/dashboard",
            "status": "success"
        }
    except Exception as e:
        return {
            "5h_window": {"quota_percent": 0, "usage_percent": 100, "reset_at": "N/A", "status": "error"},
            "weekly": {"quota_percent": 0, "usage_percent": 0, "reset_at": "N/A", "status": "error"},
            "error": str(e)
        }

def check_kimi_quota():
    """Check Kimi quota - screenshot based."""
    try:
        # Kimi uses browser automation, return cached screenshot info
        screenshot_path = Path(__file__).parent / "output" / "screenshots" / "kimi_dashboard.png"
        
        return {
            "5h_window": {
                "quota_percent": 0,
                "usage_percent": 0,
                "reset_at": "N/A",
                "status": "success",
                "note": "Screenshot-based check"
            },
            "weekly": {
                "quota_percent": 0,
                "usage_percent": 0,
                "reset_at": "N/A",
                "status": "success",
                "note": "Screenshot-based check"
            },
            "screenshot": str(screenshot_path) if screenshot_path.exists() else None,
            "status": "success"
        }
    except Exception as e:
        return {
            "5h_window": {"quota_percent": 0, "usage_percent": 100, "reset_at": "N/A", "status": "error"},
            "weekly": {"quota_percent": 0, "usage_percent": 0, "reset_at": "N/A", "status": "error"},
            "error": str(e)
        }

def check_anthropic_quota():
    """Check Anthropic quota - requires API key."""
    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return {
                "5h_window": {"quota_percent": 0, "usage_percent": 100, "reset_at": "N/A", "status": "error"},
                "weekly": {"quota_percent": 0, "usage_percent": 0, "reset_at": "N/A", "status": "error"},
                "error": "Missing API key (ANTHROPIC_API_KEY)"
            }
        
        # Anthropic quota API (adjust as needed)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "x-api-key": api_key
        }
        response = requests.get("https://api.anthropic.com/v1/usage/quota", headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "5h_window": {
                    "quota_percent": data.get("5h_quota_percent", 0),
                    "usage_percent": data.get("5h_usage_percent", 100),
                    "reset_at": data.get("5h_reset_at", "N/A"),
                    "status": "success"
                },
                "weekly": {
                    "quota_percent": data.get("weekly_quota_percent", 0),
                    "usage_percent": data.get("weekly_usage_percent", 0),
                    "reset_at": data.get("weekly_reset_at", "N/A"),
                    "status": "success"
                },
                "status": "success"
            }
        else:
            return {
                "5h_window": {"quota_percent": 0, "usage_percent": 100, "reset_at": "N/A", "status": "error"},
                "weekly": {"quota_percent": 0, "usage_percent": 0, "reset_at": "N/A", "status": "error"},
                "error": f"API error: {response.status_code}"
            }
    except Exception as e:
        return {
            "5h_window": {"quota_percent": 0, "usage_percent": 100, "reset_at": "N/A", "status": "error"},
            "weekly": {"quota_percent": 0, "usage_percent": 0, "reset_at": "N/A", "status": "error"},
            "error": str(e)
        }

def main():
    """Run all quota checks and save results."""
    print("🔍 Starting LLM Quota Check...")
    print("=" * 40)
    
    results = {}
    
    # Check each provider
    print("Checking Z.AI...")
    results["zai"] = check_zai_quota()
    print(f"  ✓ Z.AI: {results['zai'].get('status', 'unknown')}")
    
    print("Checking MiniMax...")
    results["minimax"] = check_minimax_quota()
    print(f"  ✓ MiniMax: {results['minimax'].get('status', 'unknown')}")
    
    print("Checking DashScope...")
    results["dashscope"] = check_dashscope_quota()
    print(f"  ✓ DashScope: {results['dashscope'].get('status', 'unknown')}")
    
    print("Checking Kimi...")
    results["kimi"] = check_kimi_quota()
    print(f"  ✓ Kimi: {results['kimi'].get('status', 'unknown')}")
    
    print("Checking Anthropic...")
    results["anthropic"] = check_anthropic_quota()
    print(f"  ✓ Anthropic: {results['anthropic'].get('status', 'unknown')}")
    
    # Add timestamp
    results["last_updated"] = datetime.now(timezone.utc).isoformat()
    
    # Save results
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print()
    print("📊 LLM Quota Dashboard")
    print("=" * 40)
    
    # Display summary
    for provider, info in results.items():
        if provider == "last_updated":
            continue
        
        if "5h_window" in info:
            used_5h = info["5h_window"].get("usage_percent", 100)
            status = info["5h_window"].get("status", "unknown")
            
            if status == "success":
                print(f"{provider:12s} [{used_5h:3.0f}% used]")
            else:
                error = info.get("error", "Unknown error")
                print(f"{provider:12s} ✗ {error[:40]}")
    
    print()
    print(f"Last updated: {results['last_updated']}")
    print()
    print(f"💾 Results saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
