import os
import requests
from werkzeug.security import generate_password_hash

# -------------------------
# TURSO HTTP CONFIG
# -------------------------
# In staging: set STAGING_TURSO_URL and STAGING_TURSO_AUTH_TOKEN.
# In production: set TURSO_URL and TURSO_AUTH_TOKEN as before.
# Staging vars take priority when present so the live DB is never touched.
_TURSO_URL        = os.environ.get("STAGING_TURSO_URL")        or os.environ.get("TURSO_URL", "")
_TURSO_AUTH_TOKEN = os.environ.get("STAGING_TURSO_AUTH_TOKEN") or os.environ.get("TURSO_AUTH_TOKEN", "")

# Log which DB is active at startup so you can confirm in Render logs
_ENV_LABEL = "STAGING" if os.environ.get("STAGING_TURSO_URL") else "PRODUCTION"
print(f"[db] Connecting to {_ENV_LABEL} Turso DB: {_TURSO_URL[:60]}...")

# Convert libsql:// URL to https:// for HTTP API
HTTP_URL = _TURSO_URL.replace("libsql://", "https://") + "/v2/pipeline"
HEADERS = {
    "Authorization": f"Bearer {_TURSO_AUTH_TOKEN}",
    "Content-Type": "application/json"
}

# -------------------------
# ROW — access by name like sqlite3.Row
# -------------------------
class Row:
    def __init__(self, columns, values):
        self._columns = columns
        self._values = values
        self._dict = dict(zip(columns, values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._dict[key]

    def __iter__(self):
        return iter(self._values)

    def keys(self):
        return self._columns

    def get(self, key, default=None):
        return self._dict.get(key, default)

    def __repr__(self):
        return str(self._dict)

# -------------------------
# CURSOR
# -------------------------
class TursoCursor:
    def __init__(self, conn):
        self._conn = conn
        self.description = None
        self.lastrowid = None
        self._rows = []
        self._columns = []

    def execute(self, sql, params=()):
        args = [{"type": _turso_type(p), "value": _turso_value(p)} for p in params]
        result = self._conn._execute(sql, args)
        cols = result.get("cols", [])
        self._columns = [c["name"] for c in cols]
        self.description = [(c["name"],) for c in cols]
        rows = result.get("rows", [])
        self._rows = [
            Row(self._columns, [_parse_value(v) for v in row])
            for row in rows
        ]
        self.lastrowid = result.get("last_insert_rowid")
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

# -------------------------
# CONNECTION
# -------------------------
class TursoConnection:
    def __init__(self):
        self._statements = []

    def _execute(self, sql, args=None):
        payload = {
            "requests": [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": sql,
                        "args": args or []
                    }
                },
                {"type": "close"}
            ]
        }
        resp = requests.post(HTTP_URL, json=payload, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        result = data["results"][0]
        if result["type"] == "error":
            raise Exception(result["error"]["message"])
        return result.get("response", {}).get("result", {})

    def cursor(self):
        return TursoCursor(self)

    def execute(self, sql, params=()):
        c = self.cursor()
        c.execute(sql, params)
        return c

    def commit(self):
        pass  # HTTP API auto-commits

    def close(self):
        pass

# -------------------------
# TYPE HELPERS
# -------------------------
def _turso_type(value):
    if value is None:
        return "null"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    return "text"

def _turso_value(value):
    if value is None:
        return None
    return str(value)

def _parse_value(v):
    if v is None or v == {"type": "null"}:
        return None
    if isinstance(v, dict):
        t = v.get("type")
        val = v.get("value")
        if t == "null" or val is None:
            return None
        if t == "integer":
            return int(val)
        if t == "float":
            return float(val)
        return val
    return v

# -------------------------
# GET DB CONNECTION
# -------------------------
def get_db():
    return TursoConnection()

# -------------------------
# PRICING PER LEVEL
# -------------------------
# Amounts in KOBO (Paystack uses lowest denomination)
LEVEL_PRICES = {
    "400": 1026375,   # ₦10,263.75
    "300": 800000,    # ₦8,000.00
    "200": 650000,    # ₦6,500.00
}

# Prices for cross-level unlocks (higher-level students buying lower-level content)
# Key: (buyer_level, target_level)
UNLOCK_PRICES = {
    ("400", "300"): 400000,   # ₦4,000.00
    ("400", "200"): 300000,   # ₦3,000.00
    ("300", "200"): 300000,   # ₦3,000.00
}

def get_main_price(level):
    """Return main subscription price in kobo for given level string."""
    return LEVEL_PRICES.get(str(level), LEVEL_PRICES["400"])

def get_unlock_price(buyer_level, target_level):
    """Return unlock price in kobo, or None if not applicable."""
    return UNLOCK_PRICES.get((str(buyer_level), str(target_level)))

# -------------------------
# INITIALIZE DATABASE
# -------------------------
def init_db():
    conn = get_db()

    # USERS — unchanged
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL, department TEXT, level TEXT,
        role TEXT DEFAULT 'student', is_suspended INTEGER DEFAULT 0,
        push_enabled INTEGER DEFAULT 0)""")

    # COURSES — NEW: level column added (default 400 so all existing courses stay visible to 400-level users)
    conn.execute("""CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_code TEXT UNIQUE NOT NULL,
        course_title TEXT NOT NULL,
        description TEXT,
        level INTEGER NOT NULL DEFAULT 400)""")

    # MATERIALS — unchanged
    conn.execute("""CREATE TABLE IF NOT EXISTS materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER NOT NULL, filename TEXT NOT NULL,
        file_type TEXT NOT NULL, title TEXT NOT NULL,
        FOREIGN KEY(course_id) REFERENCES courses(id))""")

    # PAYMENTS — unchanged
    conn.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, amount INTEGER NOT NULL,
        status TEXT DEFAULT 'unpaid',
        admin_override_status TEXT DEFAULT NULL,
        reference TEXT, paid_at DATETIME,
        FOREIGN KEY(user_id) REFERENCES users(id))""")

    # CONTACT MESSAGES — unchanged
    conn.execute("""CREATE TABLE IF NOT EXISTS contact_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, email TEXT NOT NULL,
        subject TEXT, message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    # NOTIFICATIONS — unchanged
    conn.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, title TEXT NOT NULL,
        message TEXT NOT NULL, link TEXT,
        is_read INTEGER DEFAULT 0, is_archived INTEGER DEFAULT 0,
        is_critical INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id))""")

    # PUSH SUBSCRIPTIONS — unchanged
    conn.execute("""CREATE TABLE IF NOT EXISTS push_subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, endpoint TEXT NOT NULL,
        p256dh TEXT NOT NULL, auth TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id))""")

    # PASSWORD RESETS — unchanged
    conn.execute("""CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token_hash TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used INTEGER DEFAULT 0)""")

    # LEVEL UNLOCKS — NEW TABLE
    # Tracks cross-level purchases: a 400-level student buying 300 or 200 level content,
    # or a 300-level student buying 200-level content.
    conn.execute("""CREATE TABLE IF NOT EXISTS level_unlocks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        target_level INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        status TEXT DEFAULT 'unpaid',
        admin_override_status TEXT DEFAULT NULL,
        reference TEXT,
        paid_at DATETIME,
        FOREIGN KEY(user_id) REFERENCES users(id))""")

    print("Database initialized successfully.")

# -------------------------
# CHECK IF ADMIN
# -------------------------
def is_admin(user_id):
    conn = get_db()
    result = conn.execute(
        "SELECT role FROM users WHERE id=?", (user_id,)
    ).fetchone()
    return result and result["role"] == "admin"

# -------------------------
# ACCESS HELPERS
# -------------------------
def get_user_level(user_id):
    """Return user's level as integer, default 400."""
    conn = get_db()
    result = conn.execute("SELECT level FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if result and result["level"]:
        try:
            return int(result["level"])
        except (ValueError, TypeError):
            return 400
    return 400

def user_can_access_level(user_id, course_level):
    """
    Returns True if the user can access content at course_level.
    Logic:
      1. Admin → always True
      2. User's own level >= course_level AND main payment is paid → True
      3. User has a paid level_unlock for that course_level → True
      4. Admin override on main payment → True
    """
    conn = get_db()
    c = conn.cursor()

    # Check admin
    c.execute("SELECT role, level FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    if not user:
        conn.close()
        return False
    if user["role"] == "admin":
        conn.close()
        return True

    user_level = int(user["level"]) if user["level"] else 400

    # Check main payment
    c.execute("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,))
    payment = c.fetchone()
    main_paid = False
    if payment:
        effective = payment["admin_override_status"] if payment["admin_override_status"] else payment["status"]
        main_paid = (effective == "paid")

    # If user's level >= course_level AND main is paid → access granted
    if main_paid and user_level >= course_level:
        conn.close()
        return True

    # Check level_unlocks for this specific course_level
    c.execute("""
        SELECT * FROM level_unlocks
        WHERE user_id=? AND target_level=?
        ORDER BY id DESC LIMIT 1
    """, (user_id, course_level))
    unlock = c.fetchone()
    if unlock:
        effective_unlock = unlock["admin_override_status"] if unlock["admin_override_status"] else unlock["status"]
        if effective_unlock == "paid":
            conn.close()
            return True

    conn.close()
    return False

def hash_password(password):
    return generate_password_hash(password)

if __name__ == "__main__":
    init_db()
