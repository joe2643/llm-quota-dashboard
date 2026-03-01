"""SQLite history storage for quota snapshots."""
import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'history.db')

def _get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute("""CREATE TABLE IF NOT EXISTS quota_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        provider TEXT NOT NULL,
        field TEXT NOT NULL,
        value REAL NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_pft ON quota_history(provider, field, timestamp)")
    db.commit()
    return db

def record_snapshot(quota_data: dict):
    """Record all *_used_pct fields from quota_data into history."""
    db = _get_db()
    ts = datetime.utcnow().isoformat() + "Z"
    rows = []
    for provider, pdata in quota_data.items():
        if provider in ('last_updated',):
            continue
        if not isinstance(pdata, dict) or pdata.get('status') != 'success':
            continue
        d = pdata.get('data', {})
        for key, val in d.items():
            if key.endswith('_used_pct') and isinstance(val, (int, float)):
                rows.append((ts, provider, key, float(val)))
    if rows:
        db.executemany("INSERT INTO quota_history(timestamp, provider, field, value) VALUES (?,?,?,?)", rows)
        db.commit()
    db.close()
    return len(rows)

def get_history(provider: str, field: str = None, hours: int = 24):
    """Get history for a provider, optionally filtered by field."""
    db = _get_db()
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat() + "Z"
    if field:
        rows = db.execute(
            "SELECT timestamp, field, value FROM quota_history WHERE provider=? AND field=? AND timestamp>? ORDER BY timestamp",
            (provider, field, cutoff)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT timestamp, field, value FROM quota_history WHERE provider=? AND timestamp>? ORDER BY timestamp",
            (provider, cutoff)
        ).fetchall()
    db.close()
    return [{"timestamp": r[0], "field": r[1], "value": r[2]} for r in rows]

def cleanup(days: int = 30):
    """Remove records older than N days."""
    db = _get_db()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat() + "Z"
    db.execute("DELETE FROM quota_history WHERE timestamp < ?", (cutoff,))
    db.commit()
    db.close()
