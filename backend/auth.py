print(">>> auth.py imported")

from flask import Blueprint, jsonify, session, request
from werkzeug.security import check_password_hash
from backend.db import get_db, is_admin
from time import time

auth_bp = Blueprint("auth_bp", __name__)

# ---------------------
# RATE LIMITING
# ---------------------
LOGIN_ATTEMPTS = {}
RATE_LIMIT_WINDOW = 300  # 5 minutes
MAX_ATTEMPTS = 5

def is_rate_limited(ip):
    now = time()
    attempts = LOGIN_ATTEMPTS.get(ip, [])
    # Remove expired attempts
    attempts = [t for t in attempts if now - t < RATE_LIMIT_WINDOW]
    LOGIN_ATTEMPTS[ip] = attempts
    return len(attempts) >= MAX_ATTEMPTS

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
        "SELECT name, department, level FROM users WHERE id=?",
        (session["user_id"],)
    )
    user = c.fetchone()
    conn.close()

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "name": user["name"],
        "department": user["department"],
        "level": user["level"]
    }), 200
    
  # ---------------------
# LOGIN
# ---------------------
@auth_bp.route("/login", methods=["POST"])
def login():
    ip = request.remote_addr or "unknown"

    # 🔐 Rate limit check
    if is_rate_limited(ip):
        return jsonify({
            "error": "Too many login attempts. Try again later."
        }), 429

    LOGIN_ATTEMPTS.setdefault(ip, []).append(time())

    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    data = request.get_json()
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

    # Invalid credentials
    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    # Suspended user
    if user["is_suspended"]:
        return jsonify({"error": "Account suspended"}), 403

    # ✅ Login success
    LOGIN_ATTEMPTS.pop(ip, None)

    # Prevent session fixation
    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]

    # Role-based redirect
    if is_admin(user["id"]):
        redirect_url = "/dashboard"
    else:
        redirect_url = "/account"

    return jsonify({
        "message": "Login successful",
        "redirect": redirect_url
    }), 200