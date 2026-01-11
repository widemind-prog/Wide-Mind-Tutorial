from flask import Blueprint, jsonify, session, request
from werkzeug.security import check_password_hash, generate_password_hash
from backend.db import get_db

auth_bp = Blueprint("auth_bp", __name__)

# Get current user info
@auth_bp.route("/me", methods=["GET"])
def me():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name, department, level FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    conn.close()

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "name": user["name"],
        "department": user["department"],
        "level": user["level"]
    }), 200

# Login route
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Missing credentials"}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, password FROM users WHERE email=?", (email,))
    user = c.fetchone()
    conn.close()

    if user and check_password_hash(user[1], password):
        session["user_id"] = user[0]
        return jsonify({"redirect": "/account"}), 200

    return jsonify({"error": "Invalid email or password"}), 401