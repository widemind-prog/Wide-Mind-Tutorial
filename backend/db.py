import os
import requests
from werkzeug.security import generate_password_hash
TURSO_URL = os.environ.get("TURSO_URL", "")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")
HTTP_URL = TURSO_URL.replace("libsql://", "https://") + "/v2/pipeline"
HEADERS = {
    "Authorization": f"Bearer {TURSO_AUTH_TOKEN}",
    "Content-Type": "application/json"
}
class Row:
    def __init__(self, columns, values):
        self._columns = columns
        self._values = values
        self._dict = dict(zip(columns, values))
    def __getitem__(self, key):
        if isinstance(key, int): return self._values[key]
        return self._dict[key]
    def __iter__(self): return iter(self._values)
    def keys(self): return self._columns
    def get(self, key, default=None): return self._dict.get(key, default)
    def __repr__(self): return str(self._dict)
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
        self._rows = [Row(self._columns, [_parse_value(v) for v in row]) for row in rows]
        self.lastrowid = result.get("last_insert_rowid")
        return self
    def fetchone(self): return self._rows[0] if self._rows else None
    def fetchall(self): return self._rows
class TursoConnection:
    def __init__(self): pass
    def _execute(self, sql, args=None):
        payload = {
            "requests": [
                {"type": "execute", "stmt": {"sql": sql, "args": args or []}},
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
    def cursor(self): return TursoCursor(self)
    def execute(self, sql, params=()):
        c = self.cursor()
        c.execute(sql, params)
        return c
    def commit(self): pass
    def close(self): pass
def _turso_type(value):
    if value is None: return "null"
    if isinstance(value, int): return "integer"
    if isinstance(value, float): return "float"
    return "text"
def _turso_value(value):
    if value is None: return None
    return str(value)
def _parse_value(v):
    if v is None or v == {"type": "null"}: return None
    if isinstance(v, dict):
        t = v.get("type")
        val = v.get("value")
        if t == "null" or val is None: return None
        if t == "integer": return int(val)
        if t == "float": return float(val)
        return val
    return v
def get_db(): return TursoConnection()
def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL, department TEXT, level TEXT,
        semester INTEGER DEFAULT 2,
        role TEXT DEFAULT 'student',
        is_suspended INTEGER DEFAULT 0,
        is_verified INTEGER DEFAULT 0,
        trial_started_at TEXT DEFAULT NULL,
        push_enabled INTEGER DEFAULT 0)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_code TEXT NOT NULL, course_title TEXT NOT NULL,
        description TEXT,
        level TEXT NOT NULL DEFAULT '400',
        semester INTEGER NOT NULL DEFAULT 2,
        is_trial INTEGER NOT NULL DEFAULT 0)""")
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
    conn.execute("""CREATE TABLE IF NOT EXISTS rerun_passes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        rerun_level TEXT NOT NULL,
        amount INTEGER NOT NULL,
        status TEXT DEFAULT 'unpaid',
        admin_override_status TEXT DEFAULT NULL,
        reference TEXT, paid_at DATETIME,
        FOREIGN KEY(user_id) REFERENCES users(id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS email_otps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        otp_hash TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        verified INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(user_id) REFERENCES users(id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        material_id INTEGER NOT NULL,
        listened_seconds REAL DEFAULT 0,
        completed INTEGER DEFAULT 0,
        opened_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, material_id),
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(material_id) REFERENCES materials(id))""")
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
    conn.execute("""CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token_hash TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used INTEGER DEFAULT 0)""")
    # Safe migrations for existing deployments
    migrations = [
        "ALTER TABLE users ADD COLUMN semester INTEGER DEFAULT 2",
        "ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN trial_started_at TEXT DEFAULT NULL",
        "ALTER TABLE courses ADD COLUMN level TEXT NOT NULL DEFAULT '400'",
        "ALTER TABLE courses ADD COLUMN semester INTEGER NOT NULL DEFAULT 2",
        "ALTER TABLE courses ADD COLUMN is_trial INTEGER NOT NULL DEFAULT 0",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except Exception:
            pass
    print("Database initialized successfully.")
def is_admin(user_id):
    conn = get_db()
    result = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
    return result and result["role"] == "admin"
def get_trial_course_for(level, semester):
    """Returns the course row flagged is_trial=1 for this exact level+semester,
    or None if no trial course has been configured for it yet. Deliberately does
    NOT fall back to a trial course from a different level/semester — a 300L
    student should never be handed a 500L trial course."""
    if level is None or semester is None:
        return None
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT * FROM courses WHERE is_trial=1 AND TRIM(level)=? AND semester=?
                 ORDER BY id DESC LIMIT 1""", (str(level).strip(), semester))
    course = c.fetchone()
    conn.close()
    return course
def hash_password(password):
    return generate_password_hash(password)
if __name__ == "__main__":
    init_db()
# Email_service.py
import os
import requests
from datetime import datetime
def send_email(to_email, subject, body):
    api_key = os.environ.get("BREVO_API_KEY")
    from_email = os.environ.get("EMAIL_FROM", "no-reply@widemindtutorial.com")
    from_name = "Wide Mind Tutorial"
    if not api_key:
        print("[EMAIL] BREVO_API_KEY missing")
        return False
    html_content = f"""
<div style="margin:0;padding:0;background-color:#fdf6e3;">
  <div style="max-width:600px;margin:0 auto;background-color:#ffffff;
              font-family:'Poppins', Arial, sans-serif;border-radius:14px;
              overflow:hidden;border:1px solid #e6d8b5;">
    <div style="background:linear-gradient(135deg,#8B7500,#d4af37);padding:25px;text-align:center;">
      <img src="https://www.widemindtutorial.com/static/images/logo.png"
           alt="Wide Mind Tutorial" style="max-width:130px;margin-bottom:12px;">
    </div>
    <div style="padding:32px;color:#3c2f1f;font-size:15px;line-height:1.7;">
      <div style="background-color:#fffaf0;padding:20px;border-radius:10px;border:1px solid #f0e6d2;">
        {body}
      </div>
      <p style="margin-top:28px;font-size:12px;color:#8B7500;">
        Sent on {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
      </p>
      <hr style="margin:25px 0;border:none;border-top:1px solid #e6d8b5;">
      <p style="font-size:13px;color:#555;margin:0;">
        This is an official email from <strong>Wide Mind Tutorial</strong>.
      </p>
      <p style="font-size:12px;color:#777;margin-top:8px;">
        Please do not reply to this message. For support, visit our website.
      </p>
    </div>
    <div style="background-color:#8B7500;padding:18px;text-align:center;
                font-size:12px;color:#f0e6d2;">
      &copy; {datetime.utcnow().year} Wide Mind Tutorial<br>
      www.widemindtutorial.com
    </div>
  </div>
</div>
"""
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json"
            },
            json={
                "sender": {"name": from_name, "email": from_email},
                "to": [{"email": to_email}],
                "subject": subject,
                "htmlContent": html_content
            },
            timeout=15
        )
        print(f"[EMAIL] Brevo status: {response.status_code} to {to_email}")
        if response.status_code not in (200, 201):
            print(f"[EMAIL] Brevo error: {response.text}")
            return False
        return True
    except Exception as e:
        print(f"[EMAIL] Failed: {type(e).__name__}: {e}")
        return False
# =====================
# OTP EMAIL
# =====================
def send_otp_email(to_email, name, otp):
    first_name = name.split()[0].capitalize()
    body = f"""
    <p style="font-size:18px;font-weight:700;color:#8B7500;">Verify Your Email Address</p>
    <p>Hi <strong>{first_name}</strong>,</p>
    <p>Enter the code below to verify your email and start your <strong>24-hour free trial</strong>.</p>
    <div style="text-align:center;margin:28px 0;">
        <div style="display:inline-block;background:linear-gradient(135deg,#8B7500,#d4af37);
                    color:#fff;font-size:36px;font-weight:800;letter-spacing:12px;
                    padding:18px 32px;border-radius:12px;">
            {otp}
        </div>
    </div>
    <p style="text-align:center;font-size:13px;color:#777;">
        This code expires in <strong>10 minutes</strong>.
    </p>
    <p style="font-size:13px;color:#aaa;">
        If you did not create an account on Wide Mind Tutorial, you can safely ignore this email.
    </p>
    """
    return send_email(to_email, "Your Wide Mind Tutorial Verification Code", body)
# =====================
# WELCOME EMAIL
# =====================
def send_welcome_email(to_email, name):
    first_name = name.split()[0].capitalize()
    body = f"""
    <p style="font-size:18px;font-weight:700;color:#8B7500;">Welcome to Wide Mind Tutorial!</p>
    <p>Hi <strong>{first_name}</strong>,</p>
    <p>
        Your account has been created. Check your email for a verification code to activate
        your <strong>24-hour free trial</strong>.
    </p>
    <p><strong>With full access you get:</strong></p>
    <ul style="padding-left:20px;line-height:2;">
        <li>Full PDF notes for all your courses</li>
        <li>Audio lectures you can listen to anywhere</li>
        <li>Real-time notifications for new materials</li>
    </ul>
    <div style="text-align:center;margin:24px 0;">
        <a href="https://www.widemindtutorial.com/verify-email"
           style="background:linear-gradient(135deg,#8B7500,#d4af37);color:#fff;
                  padding:14px 32px;border-radius:8px;text-decoration:none;
                  font-weight:bold;font-size:15px;">
            Verify My Email
        </a>
    </div>
    <p>Welcome aboard!<br><strong>Wide Mind Tutorial Team</strong></p>
    """
    return send_email(to_email, "Welcome to Wide Mind Tutorial — Verify Your Email", body)
# =====================
# PAYMENT SUCCESS EMAIL
# =====================
def send_payment_success_email(to_email, name):
    first_name = name.split()[0].capitalize()
    body = f"""
    <p style="font-size:18px;font-weight:700;color:#8B7500;">Payment Confirmed!</p>
    <p>Hi <strong>{first_name}</strong>,</p>
    <p>Your payment has been received and your account is now <strong>fully active</strong>.</p>
    <p><strong>You can now access:</strong></p>
    <ul style="padding-left:20px;line-height:2;">
        <li>PDF notes for all your courses</li>
        <li>Audio lectures for all sessions</li>
        <li>Push notifications for new uploads</li>
    </ul>
    <div style="text-align:center;margin:24px 0;">
        <a href="https://www.widemindtutorial.com/account"
           style="background:linear-gradient(135deg,#8B7500,#d4af37);color:#fff;
                  padding:14px 32px;border-radius:8px;text-decoration:none;
                  font-weight:bold;font-size:15px;">
            Go to My Account
        </a>
    </div>
    <p>Study hard and excel!<br><strong>Wide Mind Tutorial Team</strong></p>
    """
    return send_email(to_email, "Payment Confirmed — Your Access is Active!", body)
# =====================
# NEW MATERIAL EMAIL
# =====================
def send_new_material_email(to_email, name, material_title, course_title, file_type, course_id):
    first_name = name.split()[0].capitalize()
    type_label = "PDF Notes" if file_type == "pdf" else "Audio Lecture"
    body = f"""
    <p style="font-size:18px;font-weight:700;color:#8B7500;">New Material Available!</p>
    <p>Hi <strong>{first_name}</strong>,</p>
    <p>A new <strong>{type_label}</strong> has just been added to your course materials.</p>
    <div style="background:#fff8e1;border:1px solid #e6d8b5;border-radius:10px;
                padding:16px;margin:20px 0;">
        <p style="margin:0;font-size:14px;color:#555;">Course</p>
        <p style="margin:4px 0 12px;font-weight:700;color:#3c2f1f;font-size:16px;">{course_title}</p>
        <p style="margin:0;font-size:14px;color:#555;">Material</p>
        <p style="margin:4px 0 0;font-weight:700;color:#3c2f1f;font-size:16px;">{material_title}</p>
    </div>
    <div style="text-align:center;margin:24px 0;">
        <a href="https://www.widemindtutorial.com/course/{course_id}"
           style="background:linear-gradient(135deg,#8B7500,#d4af37);color:#fff;
                  padding:14px 32px;border-radius:8px;text-decoration:none;
                  font-weight:bold;font-size:15px;">
            View Material
        </a>
    </div>
    <p>Keep studying!<br><strong>Wide Mind Tutorial Team</strong></p>
    """
    return send_email(to_email, f"New {type_label} Available — {course_title}", body)
# [Otp.py](http://otp.py)
from flask import Blueprint, jsonify, session, request
from backend.db import get_db
from backend.email_service import send_otp_email
import hashlib
import random
from datetime import datetime, timedelta
otp_bp = Blueprint("otp_bp", __name__)
def _hash_otp(otp): return hashlib.sha256(str(otp).encode()).hexdigest()
def _generate_otp(): return str(random.randint(100000, 999999))
# =====================
# SEND / RESEND OTP
# =====================
@otp_bp.route("/api/otp/send", methods=["POST"])
def send_otp():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    conn = get_db()
    c = conn.cursor()
    # Enforce 60-second cooldown
    c.execute("""
        SELECT created_at FROM email_otps
        WHERE user_id=? ORDER BY id DESC LIMIT 1
    """, (session["user_id"],))
    last = c.fetchone()
    if last and last["created_at"]:
        try:
            last_time = datetime.strptime(last["created_at"], "%Y-%m-%d %H:%M:%S")
            elapsed = (datetime.utcnow() - last_time).total_seconds()
            if elapsed < 60:
                conn.close()
                return jsonify({"error": f"Please wait {int(60 - elapsed)} seconds before resending"}), 429
        except Exception:
            pass
    # Get user email
    c.execute("SELECT email, name FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "User not found"}), 404
    otp = _generate_otp()
    otp_hash = _hash_otp(otp)
    expires_at = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    # Delete old OTPs for this user, insert fresh one
    c.execute("DELETE FROM email_otps WHERE user_id=?", (session["user_id"],))
    c.execute("""
        INSERT INTO email_otps (user_id, otp_hash, expires_at, verified)
        VALUES (?, ?, ?, 0)
    """, (session["user_id"], otp_hash, expires_at))
    conn.commit()
    conn.close()
    try:
        send_otp_email(user["email"], user["name"], otp)
    except Exception as e:
        print(f"[OTP] Email failed: {e}")
        return jsonify({"error": "Failed to send OTP email. Please try again."}), 500
    return jsonify({"message": "OTP sent to your email"}), 200
# =====================
# VERIFY OTP
# =====================
@otp_bp.route("/api/otp/verify", methods=["POST"])
def verify_otp():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json() or {}
    otp_input = str(data.get("otp", "")).strip()
    if not otp_input or len(otp_input) != 6:
        return jsonify({"error": "Enter the 6-digit OTP"}), 400
    otp_hash = _hash_otp(otp_input)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, expires_at, verified FROM email_otps
        WHERE user_id=? AND otp_hash=?
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"], otp_hash))
    record = c.fetchone()
    if not record:
        conn.close()
        return jsonify({"error": "Invalid OTP"}), 400
    if record["verified"]:
        conn.close()
        return jsonify({"error": "OTP already used"}), 400
    if now > record["expires_at"]:
        conn.close()
        return jsonify({"error": "OTP has expired. Request a new one."}), 400
    # Mark OTP used, verify user, start trial
    c.execute("UPDATE email_otps SET verified=1 WHERE id=?", (record["id"],))
    c.execute("""
        UPDATE users
        SET is_verified=1,
            trial_started_at=datetime('now')
        WHERE id=?
    """, (session["user_id"],))
    conn.commit()
    conn.close()
    return jsonify({"message": "Email verified!", "redirect": "/account"}), 200
# [Payment.py](http://payment.py)
