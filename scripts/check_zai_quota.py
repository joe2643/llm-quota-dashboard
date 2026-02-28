"""
Z.AI Quota Check - Support both 5h window and weekly quota
"""
import requests
import os
from datetime import datetime, timezone

def check_zai_quota():
    """Check Z.AI quota via API - both 5h window and weekly."""
    try:
        api_key = os.getenv("ZAI_API_KEY")
        if not api_key:
            return {"status": "error", "message": "Missing API key (ZAI_API_KEY)"}
        
        # Z.AI quota API endpoint
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get("https://api.z.ai/api/v1/usage/quota", headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Support both old and new API format
            if "5h_window" in data:
                # New format with separate 5h and weekly
                result = {
                    "status": "success",
                    "5h_window": {
                        "quota_percent": data["5h_window"].get("quota_percent", 0),
                        "usage_percent": data["5h_window"].get("usage_percent", 100),
                        "reset_at": data["5h_window"].get("reset_at"),
                    },
                    "weekly": {
                        "quota_percent": data["weekly"].get("quota_percent", 0),
                        "usage_percent": data["weekly"].get("usage_percent", 100),
                        "reset_at": data["weekly"].get("reset_at"),
                    },
                    "last_checked": datetime.now(timezone.utc).isoformat()
                }
            else:
                # Old format (assume 5h window)
                result = {
                    "status": "success",
                    "5h_window": {
                        "quota_percent": data.get("quota_percent", 0),
                        "usage_percent": data.get("usage_percent", 100),
                        "reset_at": data.get("reset_at"),
                    },
                    "weekly": {
                        "quota_percent": data.get("weekly_quota_percent", 0),
                        "usage_percent": data.get("weekly_usage_percent", 0),
                        "reset_at": data.get("weekly_reset_at"),
                    },
                    "tokens_used": data.get("tokens_used", 0),
                    "tokens_limit": data.get("tokens_limit", 1),
                    "last_checked": datetime.now(timezone.utc).isoformat()
                }
            
            return result
        else:
            return {"status": "error", "message": f"API error: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    result = check_zai_quota()
    print(f"Z.AI Quota Check Result: {result}")
