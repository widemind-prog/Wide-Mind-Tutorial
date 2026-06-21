from flask import Blueprint, jsonify, session, request
from backend.db import get_db, get_trial_course_for
import os
from datetime import datetime, timedelta
progress_bp = Blueprint("progress_bp", __name__)
TRIAL_HOURS = 24
def get_trial_status(user):
    """Returns dict with trial info given a user row."""
    trial_started_at = user["trial_started_at"]
    if not trial_started_at:
        return {"active": False, "expired": False, "seconds_remaining": 0}
    try:
        started = datetime.strptime(trial_started_at, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return {"active": False, "expired": False, "seconds_remaining": 0}
    expires = started + timedelta(hours=TRIAL_HOURS)
    now = datetime.utcnow()
    if now < expires:
        remaining = int((expires - now).total_seconds())
        return {"active": True, "expired": False, "seconds_remaining": remaining}
    return {"active": False, "expired": True, "seconds_remaining": 0}
# =====================
# PROGRESS SUMMARY
# =====================
@progress_bp.route("/api/progress/summary")
def progress_summary():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    conn = get_db()
    c = conn.cursor()
    # User + payment
    c.execute("""
        SELECT u.name, u.level, u.semester, u.is_verified, u.trial_started_at,
               COALESCE(p.admin_override_status, p.status) AS payment_status,
               p.amount
        FROM users u
        LEFT JOIN payments p ON u.id=p.user_id
        WHERE u.id=?
        ORDER BY p.id DESC LIMIT 1
    """, (session["user_id"],))
    user = c.fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "User not found"}), 404
    is_paid = user["payment_status"] == "paid"
    trial = get_trial_status(user)
    trial_course = None
    if trial["active"]:
        tc = get_trial_course_for(user["level"], user["semester"])
        if tc:
            trial_course = {"id": tc["id"], "code": tc["course_code"], "title": tc["course_title"]}
    # Total audios for this user's level+semester
    c.execute("""
        SELECT COUNT(m.id) AS total FROM materials m
        JOIN courses co ON m.course_id=co.id
        WHERE co.level=? AND co.semester=? AND m.file_type='audio'
    """, (user["level"], user["semester"]))
    total_audios = c.fetchone()["total"] or 0
    # Progress stats
    c.execute("""
        SELECT SUM(pr.listened_seconds) AS total_seconds,
               SUM(CASE WHEN pr.completed=1 THEN 1 ELSE 0 END) AS completed_count
        FROM progress pr
        JOIN materials m ON pr.material_id=m.id
        JOIN courses co ON m.course_id=co.id
        WHERE pr.user_id=? AND m.file_type='audio'
        AND co.level=? AND co.semester=?
    """, (session["user_id"], user["level"], user["semester"]))
    prog = c.fetchone()
    total_listened = int(prog["total_seconds"] or 0)
    completed_count = int(prog["completed_count"] or 0)
    pending_count = max(0, total_audios - completed_count)
    conn.close()
    amount = user["amount"] or 0
    return jsonify({
        "name": user["name"],
        "is_paid": is_paid,
        "is_verified": bool(user["is_verified"]),
        "trial_active": trial["active"],
        "trial_expired": trial["expired"],
        "trial_seconds_remaining": trial["seconds_remaining"],
        "trial_course": trial_course,
        "completed_count": completed_count,
        "total_audios": total_audios,
        "pending_count": pending_count,
        "total_listened_seconds": total_listened,
        "amount": amount,
        "amount_display": f"₦{amount/100:,.2f}"
    })
# =====================
# PROGRESS UPDATE
# =====================
@progress_bp.route("/api/progress/update", methods=["POST"])
def update_progress():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json() or {}
    material_id = data.get("material_id")
    listened_seconds = float(data.get("listened_seconds", 0))
    duration_seconds = float(data.get("duration_seconds", 0))
    if not material_id:
        return jsonify({"error": "material_id required"}), 400
    completed = 1 if duration_seconds > 0 and (listened_seconds / duration_seconds) >= 0.9 else 0
    conn = get_db()
    c = conn.cursor()
    # INSERT OR IGNORE then UPDATE pattern for UNIQUE constraint
    c.execute("""
        INSERT OR IGNORE INTO progress (user_id, material_id, listened_seconds, completed, opened_at, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
    """, (session["user_id"], material_id, listened_seconds, completed))
    c.execute("""
        UPDATE progress
        SET listened_seconds = MAX(listened_seconds, ?),
            completed = MAX(completed, ?),
            updated_at = datetime('now')
        WHERE user_id=? AND material_id=?
    """, (listened_seconds, completed, session["user_id"], material_id))
    conn.commit()
    conn.close()
    return jsonify({"saved": True, "completed": bool(completed)}), 200
# =====================
# PDF OPEN TRACKING
# =====================
@progress_bp.route("/api/progress/open-pdf", methods=["POST"])
def open_pdf():
    if "user_id" not in session:
        return jsonify({"ok": True}), 200
    data = request.get_json() or {}
    material_id = data.get("material_id")
    if not material_id:
        return jsonify({"ok": True}), 200
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO progress (user_id, material_id, listened_seconds, completed, opened_at, updated_at)
        VALUES (?, ?, 0, 0, datetime('now'), datetime('now'))
    """, (session["user_id"], material_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 200
# Socket_events.py
