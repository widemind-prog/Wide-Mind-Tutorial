import os
import requests
from werkzeug.security import generate_password_hash

# -----------------------
# TURSO HTTP CONFIG
# -----------------------
TURSO_URL = os.environ.get("TURSO_URL", "")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")

# Convert libsql:// URL to https:// for HTTP API
HTTP_URL = TURSO_URL.replace("libsql://", "https://") + "/v2/pipeline"
HEADERS = {
    "Authorization": f"Bearer {TURSO_AUTH_TOKEN}",
    "Content-Type": "application/json"
}


# -----------------------
# ROW — access by name like sqlite3.Row
# -----------------------
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


# -----------------------
# CURSOR
# -----------------------
class TursoCursor:
    def __init__(self, conn):
        self._conn = conn
        self.description = None
        self.lastrowid = None
        self._rows = []
        self._columns = []

    def execute(self, sql, params=()):
        # Convert ? placeholders and Python params to Turso format
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


# -----------------------
# CONNECTION
# -----------------------
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


# -----------------------
# TYPE HELPERS
# -----------------------
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


# -----------------------
# GET DB CONNECTION
# -----------------------
def get_db():
    return TursoConnection()


# -----------------------
# INITIALIZE DATABASE
# -----------------------
def init_db():
    conn = get_db()

    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL, department TEXT, level TEXT,
        role TEXT DEFAULT 'student', is_suspended INTEGER DEFAULT 0,
        push_enabled INTEGER DEFAULT 0)""")

    conn.execute("""CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_code TEXT UNIQUE NOT NULL,
        course_title TEXT NOT NULL, description TEXT)""")

    conn.execute("""CREATE TABLE IF NOT EXISTS materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER NOT NULL, filename TEXT NOT NULL,
        file_type TEXT NOT NULL, title TEXT NOT NULL,
        FOREIGN KEY(course_id) REFERENCES courses(id))""")

    conn.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, amount INTEGER NOT NULL,
        status TEXT DEFAULT 'unpaid',
        admin_override_status TEXT DEFAULT NULL,
        reference TEXT, paid_at DATETIME,
        FOREIGN KEY(user_id) REFERENCES users(id))""")

    conn.execute("""CREATE TABLE IF NOT EXISTS contact_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, email TEXT NOT NULL,
        subject TEXT, message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    conn.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, title TEXT NOT NULL,
        message TEXT NOT NULL, link TEXT,
        is_read INTEGER DEFAULT 0, is_archived INTEGER DEFAULT 0,
        is_critical INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id))""")

    conn.execute("""CREATE TABLE IF NOT EXISTS push_subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, endpoint TEXT NOT NULL,
        p256dh TEXT NOT NULL, auth TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id))""")

    print("Database initialized successfully.")


# -----------------------
# CHECK IF ADMIN
# -----------------------
def is_admin(user_id):
    conn = get_db()
    result = conn.execute(
        "SELECT role FROM users WHERE id=?", (user_id,)
    ).fetchone()
    return result and result["role"] == "admin"


def hash_password(password):
    return generate_password_hash(password)


if __name__ == "__main__":
    init_db()
