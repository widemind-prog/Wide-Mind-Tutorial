from flask import Blueprint, jsonify, session
from backend.db import get_db

auth_bp = Blueprint("auth_bp", __name__)

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