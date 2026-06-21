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
# PROGRESS SUMMARY — per-course percentage:
#   course % = (seconds credited / total course duration seconds) * 100
# Audio materials: credited seconds = MIN(listened_seconds, duration_seconds),
#   capped so a stray over-report can never push a single lesson past 100%.
# PDF materials: a one-time flip — either fully credited (opened) or not
#   credited at all (never opened). No partial state exists for a PDF.
# Every material's weight in the total is its own duration_seconds, set by
# the admin at upload time (see admin.py add_material/edit_material). This
# is a deliberate design choice: client-reported audio.duration is exactly
# the kind of value that has caused every prior version of this feature to
# misbehave (redirected streaming URLs, metadata not loaded yet, browser
# quirks) — duration_seconds is instead a fixed, known fact set once by a
# human, so the percentage is fully deterministic and never depends on what
# happened to load correctly in any given browser session.
# =====================
@progress_bp.route("/api/progress/summary")
def progress_summary():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    conn = get_db()
    c = conn.cursor()
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

    # Exact same access scope as check_course_access() in app.py:
    #   - paid: own level+semester, plus any lower level (same semester)
    #     they hold a paid rerun pass for
    #   - trial: only the single course flagged as their trial course
    #   - unpaid / expired trial: nothing
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

    courses_out = []
    overall_credited = 0
    overall_total = 0
    if course_ids:
        placeholders = ",".join("?" for _ in course_ids)
        # Every material across the accessible courses, with this user's
        # logged progress for it (0 if never touched — LEFT JOIN, not INNER).
        c.execute(f"""
            SELECT m.id AS material_id, m.course_id AS course_id, m.file_type,
                   m.duration_seconds,
                   co.course_code, co.course_title,
                   COALESCE(pr.listened_seconds, 0) AS listened_seconds,
                   COALESCE(pr.completed, 0) AS completed
            FROM materials m
            JOIN courses co ON m.course_id = co.id
            LEFT JOIN progress pr ON pr.material_id = m.id AND pr.user_id = ?
            WHERE m.course_id IN ({placeholders})
            ORDER BY co.level DESC, co.id ASC, m.id ASC
        """, [session["user_id"]] + course_ids)
        rows = c.fetchall()

        by_course = {}
        for row in rows:
            cid = row["course_id"]
            if cid not in by_course:
                by_course[cid] = {
                    "course_id": cid,
                    "course_code": row["course_code"],
                    "course_title": row["course_title"],
                    "credited_seconds": 0,
                    "total_seconds": 0,
                    "material_count": 0,
                    "configured_count": 0,  # materials with a real duration_seconds set
                }
            entry = by_course[cid]
            duration = int(row["duration_seconds"] or 0)
            entry["material_count"] += 1
            if duration <= 0:
                # Admin hasn't set a duration for this material yet — it
                # can't contribute to the percentage in either direction,
                # so it's excluded from both numerator and denominator
                # rather than silently treated as 0-length (which would
                # otherwise let it inflate the denominator with no way to
                # ever be credited).
                continue
            entry["configured_count"] += 1
            entry["total_seconds"] += duration
            if row["file_type"] == "pdf":
                if row["completed"]:
                    entry["credited_seconds"] += duration
            else:
                listened = float(row["listened_seconds"] or 0)
                entry["credited_seconds"] += min(listened, duration)

        for cid in course_ids:
            entry = by_course.get(cid)
            if not entry:
                continue
            pct = round((entry["credited_seconds"] / entry["total_seconds"]) * 100) if entry["total_seconds"] > 0 else 0
            pct = max(0, min(100, pct))
            overall_credited += entry["credited_seconds"]
            overall_total += entry["total_seconds"]
            courses_out.append({
                "course_id": entry["course_id"],
                "course_code": entry["course_code"],
                "course_title": entry["course_title"],
                "percent": pct,
                "credited_seconds": int(entry["credited_seconds"]),
                "total_seconds": int(entry["total_seconds"]),
                "material_count": entry["material_count"],
                "unconfigured_count": entry["material_count"] - entry["configured_count"],
            })

    overall_percent = round((overall_credited / overall_total) * 100) if overall_total > 0 else 0
    overall_percent = max(0, min(100, overall_percent))
    conn.close()
    amount = get_amount_for_level(user["level"])
    response = jsonify({
        "name": user["name"],
        "is_paid": is_paid,
        "is_verified": bool(user["is_verified"]),
        "trial_active": trial["active"],
        "trial_expired": trial["expired"],
        "trial_seconds_remaining": trial["seconds_remaining"],
        "trial_course": trial_course,
        "courses": courses_out,
        "overall_percent": overall_percent,
        "overall_credited_seconds": int(overall_credited),
        "overall_total_seconds": int(overall_total),
        "amount": amount,
        "amount_display": f"₦{amount/100:,.2f}"
    })
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response
# =====================
# PROGRESS UPDATE — audio only. The client reports listened_seconds (current
# playback position); duration is never taken from the client. It's looked
# up from materials.duration_seconds (set once by the admin at upload time)
# so an audio.duration that failed to load correctly in some browser can
# never corrupt the stored progress. completed is derived server-side too.
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
    listened_seconds = float(data.get("listened_seconds", 0) or 0)
    if not material_id:
        return jsonify({"error": "material_id required"}), 400
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT duration_seconds, file_type FROM materials WHERE id=?", (material_id,))
    material = c.fetchone()
    if not material:
        conn.close()
        return jsonify({"error": "material not found"}), 404
    duration = int(material["duration_seconds"] or 0)
    # Cap at the known duration so a stray client value (e.g. seeking past
    # the reported end, or a metadata glitch) can never push a single
    # material's credited time past its real length.
    if duration > 0:
        listened_seconds = min(listened_seconds, duration)
    completed = 1 if duration > 0 and (listened_seconds / duration) >= 0.9 else 0
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
# PDF OPEN TRACKING — one-time flip: opened or not opened, nothing in between
# =====================
@progress_bp.route("/api/progress/open-pdf", methods=["POST"])
def open_pdf():
    if "user_id" not in session:
        return jsonify({"ok": True}), 200
    data = request.get_json(force=True, silent=True) or {}
    material_id = data.get("material_id")
    if not material_id:
        return jsonify({"ok": True}), 200
    conn = get_db()
    c = conn.cursor()
    # A PDF has no "partially read" concept here — the moment it's opened for
    # the first time it flips straight to completed=1. INSERT OR IGNORE means
    # this is genuinely one-time: re-opening the same PDF later does nothing
    # further (the UPDATE below is a harmless no-op once completed is already 1).
    c.execute("""
        INSERT OR IGNORE INTO progress (user_id, material_id, listened_seconds, completed, opened_at, updated_at)
        VALUES (?, ?, 0, 1, datetime('now'), datetime('now'))
    """, (session["user_id"], material_id))
    c.execute("""
        UPDATE progress SET completed=1, updated_at=datetime('now')
        WHERE user_id=? AND material_id=?
    """, (session["user_id"], material_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 200
