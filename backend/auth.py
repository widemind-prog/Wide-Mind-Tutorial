from flask import Blueprint, jsonify, session, request
from werkzeug.security import check_password_hash
from backend.db import get_db, is_admin

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

    # User not found
    if not user:
        return jsonify({"error": "Invalid email or password"}), 401

    # User suspended
    if user["is_suspended"]:
        return jsonify({"error": "Account suspended"}), 403

    # Password check
    if not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    # ✅ Login success
    session.permanent = True
    session["user_id"] = user["id"]

    # Redirect based on role
    if is_admin(user["id"]):
        return jsonify({"redirect": "/admin"}), 200
    else:
        return jsonify({"redirect": "/account"}), 200