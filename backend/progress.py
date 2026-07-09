from flask import Blueprint, jsonify, session, request
from datetime import datetime, timedelta
from backend.db import get_db, get_trial_course_for
from backend.payment import get_amount_for_level

progress_bp = Blueprint("progress_bp", __name__)

TRIAL_HOURS = 24


def get_trial_status(user):
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
# Per-course percentage: (credited_seconds / total_seconds) * 100
# Audio: credited = min(listened_seconds, duration_seconds)
# PDF:   credited = duration_seconds if opened (completed=1), else 0
# duration_seconds is set by admin at upload time — never taken from client
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
            trial_course = {
                "id": tc["id"],
                "code": tc["course_code"],
                "title": tc["course_title"]
            }

    # Resolve accessible course IDs — mirrors check_course_access() in app.py
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
            ph = ",".join("?" for _ in rerun_levels)
            c.execute(f"SELECT id FROM courses WHERE semester=? AND level IN ({ph})",
                      [user["semester"]] + rerun_levels)
            course_ids.extend([row["id"] for row in c.fetchall()])
    elif trial_course:
        course_ids = [trial_course["id"]]

    courses_out = []
    overall_credited = 0
    overall_total = 0

    if course_ids:
        ph = ",".join("?" for _ in course_ids)
        c.execute(f"""
            SELECT m.id AS material_id, m.course_id, m.file_type, m.duration_seconds,
                   co.course_code, co.course_title,
                   COALESCE(pr.listened_seconds, 0) AS listened_seconds,
                   COALESCE(pr.completed, 0) AS completed
            FROM materials m
            JOIN courses co ON m.course_id = co.id
            LEFT JOIN progress pr ON pr.material_id = m.id AND pr.user_id = ?
            WHERE m.course_id IN ({ph})
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
                    "credited": 0,
                    "total": 0,
                    "mat_count": 0,
                    "configured_count": 0,
                }
            entry = by_course[cid]
            duration = int(row["duration_seconds"] or 0)
            entry["mat_count"] += 1
            if duration <= 0:
                continue
            entry["configured_count"] += 1
            entry["total"] += duration
            if row["file_type"] == "pdf":
                if row["completed"]:
                    entry["credited"] += duration
            else:
                entry["credited"] += min(float(row["listened_seconds"] or 0), duration)

        for cid in course_ids:
            entry = by_course.get(cid)
            if not entry:
                continue
            pct = round((entry["credited"] / entry["total"]) * 100) if entry["total"] > 0 else 0
            pct = max(0, min(100, pct))
            overall_credited += entry["credited"]
            overall_total += entry["total"]
            courses_out.append({
                "course_id": entry["course_id"],
                "course_code": entry["course_code"],
                "course_title": entry["course_title"],
                "percent": pct,
                "credited_seconds": int(entry["credited"]),
                "total_seconds": int(entry["total"]),
                "material_count": entry["mat_count"],
                "unconfigured_count": entry["mat_count"] - entry["configured_count"],
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
        "amount_display": f"\u20a6{amount/100:,.2f}"
    })
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response


# =====================
# PROGRESS UPDATE — audio only
# Client reports listened_seconds (playback position only — no duration)
# Duration is looked up server-side from materials.duration_seconds
# =====================
@progress_bp.route("/api/progress/update", methods=["POST"])
def update_progress():
    if "user_id" not in session:
        print("[PROGRESS] update_progress: no user_id in session")
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json(force=True, silent=True) or {}
    material_id = data.get("material_id")
    listened_seconds = float(data.get("listened_seconds", 0) or 0)
    print(f"[PROGRESS] update called: user={session['user_id']} material={material_id} listened={listened_seconds}")
    if not material_id:
        print("[PROGRESS] update_progress: no material_id in payload")
        return jsonify({"error": "material_id required"}), 400

    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT duration_seconds FROM materials WHERE id=?", (material_id,))
        material = c.fetchone()
        if not material:
            conn.close()
            print(f"[PROGRESS] material {material_id} not found in DB")
            return jsonify({"error": "material not found"}), 404

        duration = int(material["duration_seconds"] or 0)
        if duration > 0:
            listened_seconds = min(listened_seconds, duration)
        completed = 1 if duration > 0 and (listened_seconds / duration) >= 0.9 else 0
        print(f"[PROGRESS] duration={duration} capped_listened={listened_seconds} completed={completed}")

        c.execute("""
            INSERT OR IGNORE INTO progress
                (user_id, material_id, listened_seconds, completed, opened_at, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (session["user_id"], material_id, listened_seconds, completed))
        print(f"[PROGRESS] INSERT done")

        c.execute("""
            UPDATE progress
            SET listened_seconds = MAX(listened_seconds, ?),
                completed = MAX(completed, ?),
                updated_at = datetime('now')
            WHERE user_id=? AND material_id=?
        """, (listened_seconds, completed, session["user_id"], material_id))
        print(f"[PROGRESS] UPDATE done")

        conn.commit()
        conn.close()
        print(f"[PROGRESS] success: user={session['user_id']} material={material_id} listened={listened_seconds}")
        return jsonify({"ok": True}), 200

    except Exception as e:
        print(f"[PROGRESS] ERROR in update_progress: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# =====================
# PDF OPEN — one-time flip to completed=1
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
    c.execute("""
        INSERT OR IGNORE INTO progress
            (user_id, material_id, listened_seconds, completed, opened_at, updated_at)
        VALUES (?, ?, 0, 1, datetime('now'), datetime('now'))
    """, (session["user_id"], material_id))
    c.execute("""
        UPDATE progress SET completed=1, updated_at=datetime('now')
        WHERE user_id=? AND material_id=?
    """, (session["user_id"], material_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True}), 200


# =====================
# DEBUG — remove after confirming progress writes work
# Hit /api/progress/debug in your browser while logged in to see your raw rows
# =====================
@progress_bp.route("/api/progress/debug")
def debug_progress():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT pr.material_id, pr.listened_seconds, pr.completed, pr.updated_at,
               m.title, m.file_type, m.duration_seconds, m.course_id
        FROM progress pr
        JOIN materials m ON pr.material_id = m.id
        WHERE pr.user_id = ?
        ORDER BY pr.updated_at DESC
    """, (session["user_id"],))
    rows = c.fetchall()
    conn.close()
    return jsonify([{
        "material_id": r["material_id"],
        "title": r["title"],
        "file_type": r["file_type"],
        "listened_seconds": r["listened_seconds"],
        "duration_seconds": r["duration_seconds"],
        "completed": r["completed"],
        "updated_at": r["updated_at"],
        "course_id": r["course_id"]
    } for r in rows])
