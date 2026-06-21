from flask import Blueprint, jsonify, session, request
from backend.db import get_db, get_trial_course_for
from backend.payment import get_amount_for_level
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
               COALESCE(p.admin_override_status, p.status) AS payment_status
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

    # Resolve the exact set of course IDs this user can currently open —
    # mirrors check_course_access() in app.py so the progress card always
    # matches what's actually unlockable, not just their home level/semester:
    #   - paid users: their own level+semester, PLUS any lower level (same
    #     semester) they hold a paid rerun pass for
    #   - trial users: only the single course flagged as their trial course
    #   - unpaid/expired-trial users: nothing yet
    course_ids = []
    if is_paid:
        c.execute("SELECT id FROM courses WHERE level=? AND semester=?",
                   (user["level"], user["semester"]))
        course_ids.extend([row["id"] for row in c.fetchall()])
        c.execute("""SELECT DISTINCT rerun_level FROM rerun_passes
                     WHERE user_id=? AND (status='paid' OR admin_override_status='paid')""",
                  (session["user_id"],))
        rerun_levels = [row["rerun_level"] for row in c.fetchall()]
        if rerun_levels:
            placeholders = ",".join("?" for _ in rerun_levels)
            c.execute(f"""SELECT id FROM courses WHERE semester=? AND level IN ({placeholders})""",
                      [user["semester"]] + rerun_levels)
            course_ids.extend([row["id"] for row in c.fetchall()])
    elif trial_course:
        course_ids = [trial_course["id"]]

    if course_ids:
        placeholders = ",".join("?" for _ in course_ids)
        c.execute(f"""SELECT COUNT(id) AS total FROM materials
                      WHERE file_type='audio' AND course_id IN ({placeholders})""", course_ids)
        total_audios = c.fetchone()["total"] or 0
        c.execute(f"""
            SELECT SUM(pr.listened_seconds) AS total_seconds,
                   SUM(CASE WHEN pr.completed=1 THEN 1 ELSE 0 END) AS completed_count
            FROM progress pr
            JOIN materials m ON pr.material_id=m.id
            WHERE pr.user_id=? AND m.file_type='audio' AND m.course_id IN ({placeholders})
        """, [session["user_id"]] + course_ids)
        prog = c.fetchone()
        total_listened = int(prog["total_seconds"] or 0)
        completed_count = int(prog["completed_count"] or 0)

        # Per-lesson breakdown — this is what actually makes the progress
        # card accountable: not just "X of Y completed" as an abstract
        # number, but the literal list of lessons it's counting, each with
        # its own listened-seconds and a direct link to resume it.
        c.execute(f"""
            SELECT m.id AS material_id, m.title AS material_title,
                   m.course_id AS course_id, co.course_code, co.course_title,
                   COALESCE(pr.listened_seconds, 0) AS listened_seconds,
                   COALESCE(pr.completed, 0) AS completed
            FROM materials m
            JOIN courses co ON m.course_id = co.id
            LEFT JOIN progress pr ON pr.material_id = m.id AND pr.user_id = ?
            WHERE m.file_type='audio' AND m.course_id IN ({placeholders})
            ORDER BY co.level DESC, co.id ASC, m.id ASC
        """, [session["user_id"]] + course_ids)
        lessons = [{
            "material_id": row["material_id"],
            "title": row["material_title"],
            "course_id": row["course_id"],
            "course_code": row["course_code"],
            "course_title": row["course_title"],
            "listened_seconds": int(row["listened_seconds"] or 0),
            "completed": bool(row["completed"])
        } for row in c.fetchall()]
    else:
        total_audios = 0
        total_listened = 0
        completed_count = 0
        lessons = []
    pending_count = max(0, total_audios - completed_count)
    conn.close()
    # Always compute the amount live from the user's current level/price
    # table — never trust payments.amount directly. A user's payment row can
    # have a stale or NULL amount (e.g. an unpaid row seeded at registration,
    # or one zeroed out by the admin "change level" force-re-pay flow), and
    # the account page must always show the correct current fee regardless.
    amount = get_amount_for_level(user["level"])
    response = jsonify({
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
        "lessons": lessons,
        "amount": amount,
        "amount_display": f"₦{amount/100:,.2f}"
    })
    # This endpoint drives the account page's progress card in real time —
    # it must never be served stale from a browser/proxy cache after a
    # reload, especially right after an admin marks the user paid.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response
# =====================
# PROGRESS UPDATE
# =====================
@progress_bp.route("/api/progress/update", methods=["POST"])
def update_progress():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    # force=True: tolerate requests that don't carry an exact
    # "Content-Type: application/json" header. navigator.sendBeacon() (used
    # by course.js to reliably flush progress on page-navigation/exit) sends
    # its payload as a Blob, and not every browser stamps the Content-Type
    # exactly the way Flask expects by default — without force=True those
    # requests would silently return None here and the whole listen session
    # would be lost, which is exactly the "0% after listening" symptom this
    # endpoint must never produce again.
    data = request.get_json(force=True, silent=True) or {}
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
