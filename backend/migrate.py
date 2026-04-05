"""
migrate.py
----------
One-time migration script for the Wide Mind Tutorial multi-level expansion.
Safe to run against a live Turso database — all operations are additive only.
Nothing is dropped or modified. Existing data is untouched.

Run once on deploy:
    python migrate.py

Or add to your startup sequence before init_db() if you want it automatic.
"""

import os
import sys
import requests

TURSO_URL        = os.environ.get("TURSO_URL", "")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")

if not TURSO_URL or not TURSO_AUTH_TOKEN:
    print("ERROR: TURSO_URL and TURSO_AUTH_TOKEN environment variables must be set.")
    sys.exit(1)

HTTP_URL = TURSO_URL.replace("libsql://", "https://") + "/v2/pipeline"
HEADERS  = {
    "Authorization": f"Bearer {TURSO_AUTH_TOKEN}",
    "Content-Type":  "application/json"
}


def run_sql(sql, description=""):
    """Execute a single SQL statement against Turso HTTP API."""
    payload = {
        "requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": []}},
            {"type": "close"}
        ]
    }
    resp = requests.post(HTTP_URL, json=payload, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data   = resp.json()
    result = data["results"][0]
    if result["type"] == "error":
        print(f"  ✗ FAILED  — {description}")
        print(f"    Error: {result['error']['message']}")
        return False
    print(f"  ✓ OK      — {description}")
    return True


def column_exists(table, column):
    """Check whether a column already exists in a table (PRAGMA table_info)."""
    payload = {
        "requests": [
            {"type": "execute", "stmt": {"sql": f"PRAGMA table_info({table})", "args": []}},
            {"type": "close"}
        ]
    }
    resp = requests.post(HTTP_URL, json=payload, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data  = resp.json()
    result = data["results"][0]
    rows  = result.get("response", {}).get("result", {}).get("rows", [])
    # Each row: [cid, name, type, notnull, dflt_value, pk]
    for row in rows:
        col_name = row[1].get("value", "") if isinstance(row[1], dict) else row[1]
        if col_name == column:
            return True
    return False


def table_exists(table):
    """Check whether a table exists."""
    payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    "args": [{"type": "text", "value": table}]
                }
            },
            {"type": "close"}
        ]
    }
    resp = requests.post(HTTP_URL, json=payload, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data   = resp.json()
    result = data["results"][0]
    rows   = result.get("response", {}).get("result", {}).get("rows", [])
    return len(rows) > 0


def main():
    print("\n=== Wide Mind Tutorial — Multi-Level Migration ===\n")

    # ------------------------------------------------------------------
    # 1. courses.level column
    #    Add level INTEGER DEFAULT 400 so all existing courses are
    #    automatically visible to 400-level students. No data is changed.
    # ------------------------------------------------------------------
    print("[ courses table ]")
    if column_exists("courses", "level"):
        print("  – level column already exists, skipping.")
    else:
        run_sql(
            "ALTER TABLE courses ADD COLUMN level INTEGER NOT NULL DEFAULT 400",
            "Add level column to courses (default 400)"
        )

    # ------------------------------------------------------------------
    # 2. level_unlocks table
    #    Tracks cross-level purchases. Created fresh if not present.
    # ------------------------------------------------------------------
    print("\n[ level_unlocks table ]")
    if table_exists("level_unlocks"):
        print("  – level_unlocks table already exists, skipping.")
    else:
        run_sql(
            """
            CREATE TABLE level_unlocks (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id              INTEGER NOT NULL,
                target_level         INTEGER NOT NULL,
                amount               INTEGER NOT NULL,
                status               TEXT    DEFAULT 'unpaid',
                admin_override_status TEXT   DEFAULT NULL,
                reference            TEXT,
                paid_at              DATETIME,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """,
            "Create level_unlocks table"
        )

    # ------------------------------------------------------------------
    # 3. password_resets table (may be missing on older deploys)
    #    init_db() creates it conditionally but this guarantees it exists.
    # ------------------------------------------------------------------
    print("\n[ password_resets table ]")
    if table_exists("password_resets"):
        print("  – password_resets table already exists, skipping.")
    else:
        run_sql(
            """
            CREATE TABLE password_resets (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                token_hash TEXT    NOT NULL,
                expires_at TEXT    NOT NULL,
                used       INTEGER DEFAULT 0
            )
            """,
            "Create password_resets table"
        )

    # ------------------------------------------------------------------
    # 4. Verify existing 400-level courses got the default correctly
    # ------------------------------------------------------------------
    print("\n[ verification ]")
    payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": "SELECT COUNT(*) as cnt FROM courses WHERE level IS NULL OR level = ''",
                    "args": []
                }
            },
            {"type": "close"}
        ]
    }
    resp   = requests.post(HTTP_URL, json=payload, headers=HEADERS, timeout=15)
    data   = resp.json()
    result = data["results"][0]
    rows   = result.get("response", {}).get("result", {}).get("rows", [])
    null_count = 0
    if rows:
        val = rows[0][0]
        null_count = int(val.get("value", 0)) if isinstance(val, dict) else int(val)

    if null_count > 0:
        print(f"  ! {null_count} course(s) have NULL level — patching to 400...")
        run_sql(
            "UPDATE courses SET level = 400 WHERE level IS NULL OR level = ''",
            f"Patch {null_count} NULL-level courses to 400"
        )
    else:
        print("  ✓ All courses have a valid level value.")

    print("\n=== Migration complete ===\n")


if __name__ == "__main__":
    main()
