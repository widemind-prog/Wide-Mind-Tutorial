from flask import Blueprint, jsonify, session, request
from werkzeug.security import check_password_hash, generate_password_hash
from backend.db import get_db, is_admin
from backend.email_service import send_email
import secrets
import hashlib
from datetime import datetime, timedelta

auth_bp = Blueprint("auth_bp", __name__)

# ---------------------
# GET CURRENT USER
# ---------------------
@auth_bp.route("/me", methods=["GET"])
def me():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT name, department, level, email, role FROM users WHERE id=?",
        (session["user_id"],)
    )
    user = c.fetchone()
    conn.close()

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "name": user["name"],
        "email": user["email"],
        "department": user["department"],
        "level": user["level"],
        "role": user["role"]
    })

# ---------------------
# LOGIN
# ---------------------
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Missing credentials"}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT id, password, is_suspended FROM users WHERE email=?",
        (email,)
    )
    user = c.fetchone()
    conn.close()

    if not user:
        return jsonify({"error": "Invalid email or password"}), 401

    if user["is_suspended"]:
        return jsonify({"error": "Account suspended"}), 403

    if not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    session.permanent = True
    session["user_id"] = user["id"]

    if is_admin(user["id"]):
        return jsonify({"redirect": "/admin"}), 200
    else:
        return jsonify({"redirect": "/account"}), 200

# ---------------------
# FORGOT PASSWORD
# ---------------------
@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()

    if not email:
        return jsonify({"error": "Email is required"}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name FROM users WHERE email=?", (email,))
    user = c.fetchone()

    # Always return success to prevent email enumeration
    if not user:
        conn.close()
        return jsonify({"message": "If that email exists, a reset link has been sent."}), 200

    # Generate secure token
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = (datetime.utcnow() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

    # Store token in db (create table if needed)
    c.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER DEFAULT 0
        )
    """)
    # Clear old tokens for this user
    c.execute("DELETE FROM password_resets WHERE user_id=?", (user["id"],))
    c.execute(
        "INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
        (user["id"], token_hash, expires_at)
    )
    conn.commit()
    conn.close()

    reset_link = f"https://www.widemindtutorial.com/reset-password?token={raw_token}"

    body = f"""
        <p>Hi <strong>{user['name']}</strong>,</p>
        <p>We received a request to reset your password for your Wide Mind Tutorial account.</p>
        <p>Click the button below to reset it. This link expires in <strong>1 hour</strong>.</p>
        <div style="text-align:center;margin:28px 0;">
            <a href="{reset_link}"
               style="background:linear-gradient(135deg,#8B7500,#d4af37);
                      color:#fff;
                      padding:14px 32px;
                      border-radius:8px;
                      text-decoration:none;
                      font-weight:bold;
                      font-size:15px;">
                Reset My Password
            </a>
        </div>
        <p style="font-size:13px;color:#777;">
            If you didn't request this, you can safely ignore this email.
            Your password will not change.
        </p>
        <p style="font-size:12px;color:#999;word-break:break-all;">
            Or copy this link: {reset_link}
        </p>
    """

    send_email(email, "Reset Your Password — Wide Mind Tutorial", body)

    return jsonify({"message": "If that email exists, a reset link has been sent."}), 200

# ---------------------
# RESET PASSWORD
# ---------------------
@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json() or {}
    raw_token = data.get("token", "").strip()
    new_password = data.get("password", "").strip()

    if not raw_token or not new_password:
        return jsonify({"error": "Token and password are required"}), 400

    if len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT user_id, expires_at, used
        FROM password_resets
        WHERE token_hash=?
    """, (token_hash,))
    record = c.fetchone()

    if not record:
        conn.close()
        return jsonify({"error": "Invalid or expired reset link"}), 400

    if record["used"]:
        conn.close()
        return jsonify({"error": "This reset link has already been used"}), 400

    expires_at = datetime.strptime(record["expires_at"], "%Y-%m-%d %H:%M:%S")
    if datetime.utcnow() > expires_at:
        conn.close()
        return jsonify({"error": "Reset link has expired. Please request a new one."}), 400

    # Update password and mark token used
    hashed = generate_password_hash(new_password)
    c.execute("UPDATE users SET password=? WHERE id=?", (hashed, record["user_id"]))
    c.execute("UPDATE password_resets SET used=1 WHERE token_hash=?", (token_hash,))
    conn.commit()
    conn.close()

    return jsonify({"message": "Password reset successful", "redirect": "/login-page"}), 200
