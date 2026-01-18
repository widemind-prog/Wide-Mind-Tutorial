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