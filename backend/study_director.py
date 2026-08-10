"""
Wide Mind Study Director — Phase 1–4
Opt-in · Student context · Content indexing · Tip library
"""

import json
from datetime import datetime

from flask import Blueprint, jsonify, redirect, render_template, request, session

from backend.db import get_db, is_admin
from backend.whatsapp import get_provider

study_director_bp = Blueprint("study_director", __name__)


# ══════════════════════════════════════════════════════════════════
# OPT-IN PAGE
# ══════════════════════════════════════════════════════════════════

@study_director_bp.route("/study-tips")
def study_tips_page():
    return render_template("study_tips.html")


# ══════════════════════════════════════════════════════════════════
# SUBSCRIBE
# ══════════════════════════════════════════════════════════════════

@study_director_bp.route("/api/study-tips/subscribe", methods=["POST"])
def subscribe():
    data       = request.get_json() or {}
    name       = (data.get("name") or "").strip()
    whatsapp   = (data.get("whatsapp") or "").strip()
    department = (data.get("department") or "").strip()
    level      = (data.get("level") or "").strip()
    semester   = data.get("semester")
    categories = data.get("categories") or []
    consent    = data.get("consent", False)

    if not all([name, whatsapp, department, level, semester]):
        return jsonify({"error": "All fields are required"}), 400
    if not consent:
        return jsonify({"error": "Please confirm your consent to receive messages"}), 400

    phone = whatsapp.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not phone.startswith("+"):
        phone = "+" + phone

    try:
        semester = int(semester)
        if semester not in (1, 2):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid semester"}), 400

    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT id, opted_out FROM study_tips_subscribers WHERE whatsapp=?", (phone,))
    existing = c.fetchone()

    if existing:
        if existing["opted_out"]:
            c.execute("""UPDATE study_tips_subscribers
                         SET opted_out=0, opted_out_at=NULL, consent=1,
                             consent_at=datetime('now'), name=?, department=?,
                             level=?, semester=?, preferred_categories=?
                         WHERE id=?""",
                      (name, department, level, semester,
                       json.dumps(categories), existing["id"]))
            conn.commit()
            conn.close()
            return jsonify({"message": "Welcome back! You've been re-subscribed."}), 200
        conn.close()
        return jsonify({"error": "This WhatsApp number is already subscribed."}), 409

    user_id = session.get("user_id")
    c.execute("""INSERT INTO study_tips_subscribers
                 (user_id, name, whatsapp, department, level, semester,
                  preferred_categories, consent, consent_at, source)
                 VALUES (?, ?, ?, ?, ?, ?, ?, 1, datetime('now'), 'website')""",
              (user_id, name, phone, department, level, semester,
               json.dumps(categories)))
    conn.commit()
    conn.close()
    return jsonify({"message": "You're in! Study tips will start arriving on WhatsApp soon."}), 200


# ══════════════════════════════════════════════════════════════════
# UNSUBSCRIBE
# ══════════════════════════════════════════════════════════════════

@study_director_bp.route("/api/study-tips/unsubscribe", methods=["POST"])
def unsubscribe():
    data  = request.get_json() or {}
    phone = (data.get("whatsapp") or "").strip()
    conn  = get_db()
    c     = conn.cursor()

    if phone:
        phone = phone.replace(" ", "").replace("-", "")
        if not phone.startswith("+"):
            phone = "+" + phone
        c.execute("""UPDATE study_tips_subscribers
                     SET opted_out=1, opted_out_at=datetime('now')
                     WHERE whatsapp=?""", (phone,))
    else:
        user_id = session.get("user_id")
        if not user_id:
            conn.close()
            return jsonify({"error": "Phone number required"}), 400
        c.execute("""UPDATE study_tips_subscribers
                     SET opted_out=1, opted_out_at=datetime('now')
                     WHERE user_id=? AND opted_out=0""", (user_id,))

    conn.commit()
    conn.close()
    return jsonify({"message": "You've been unsubscribed from Wide Mind Study Tips."}), 200


# ══════════════════════════════════════════════════════════════════
# STUDENT CONTEXT ENGINE (Phase 2)
# ══════════════════════════════════════════════════════════════════

def build_student_context(subscriber_id: int) -> dict | None:
    """
    Assembles the full context profile for a subscriber.
    Used by the Study Director to decide what tip to send next.
    Returns None if subscriber not found or has opted out.
    """
    conn = get_db()
    c    = conn.cursor()

    c.execute("""SELECT s.*, u.name AS account_name
                 FROM study_tips_subscribers s
                 LEFT JOIN users u ON s.user_id=u.id
                 WHERE s.id=? AND s.opted_out=0""", (subscriber_id,))
    sub = c.fetchone()
    if not sub:
        conn.close()
        return None

    user_level = str(sub["level"]).strip()
    try:
        user_semester = int(str(sub["semester"]).strip())
    except (TypeError, ValueError):
        user_semester = sub["semester"]

    # Courses for this level/semester
    c.execute("""SELECT id, course_code, course_title, description
                 FROM courses WHERE TRIM(level)=? AND semester=?
                 ORDER BY course_code""",
              (user_level, user_semester))
    courses    = [dict(r) for r in c.fetchall()]
    course_ids = [co["id"] for co in courses]

    # Materials per course
    materials_by_course = {}
    if course_ids:
        ph = ",".join("?" * len(course_ids))
        c.execute(f"""SELECT id, course_id, title, file_type
                      FROM materials WHERE course_id IN ({ph})
                      ORDER BY course_id, id""", course_ids)
        for row in c.fetchall():
            cid = row["course_id"]
            materials_by_course.setdefault(cid, []).append(dict(row))

    # Progress — only if subscriber has a linked account
    progress_by_course = {}
    if sub["user_id"] and course_ids:
        ph = ",".join("?" * len(course_ids))
        c.execute(f"""SELECT m.course_id,
                             COUNT(m.id) AS total,
                             SUM(CASE WHEN pr.completed=1 THEN 1 ELSE 0 END) AS completed
                      FROM materials m
                      LEFT JOIN progress pr
                             ON pr.material_id=m.id AND pr.user_id=?
                      WHERE m.course_id IN ({ph}) AND m.file_type='audio'
                      GROUP BY m.course_id""",
                  [sub["user_id"]] + course_ids)
        for row in c.fetchall():
            progress_by_course[row["course_id"]] = {
                "total": row["total"],
                "completed": row["completed"] or 0,
            }

    # Last 10 messages for repetition avoidance
    c.execute("""SELECT tip_id, category, course_id, sent_at
                 FROM study_director_messages
                 WHERE subscriber_id=? AND status IN ('sent','delivered','read')
                 ORDER BY sent_at DESC LIMIT 10""", (subscriber_id,))
    recent_messages = [dict(r) for r in c.fetchall()]

    # Category distribution for balance
    c.execute("""SELECT category, COUNT(*) AS cnt
                 FROM study_director_messages
                 WHERE subscriber_id=?
                 GROUP BY category""", (subscriber_id,))
    category_counts = {r["category"]: r["cnt"] for r in c.fetchall()}

    conn.close()

    preferred = []
    try:
        preferred = json.loads(sub["preferred_categories"] or "[]")
    except Exception:
        pass

    return {
        "subscriber_id": subscriber_id,
        "name":          sub["name"],
        "department":    sub["department"],
        "level":         user_level,
        "semester":      user_semester,
        "preferred_categories": preferred,
        "courses":              courses,
        "materials_by_course":  materials_by_course,
        "progress_by_course":   progress_by_course,
        "recent_messages":      recent_messages,
        "category_counts":      category_counts,
        "user_id":              sub["user_id"],
    }


# ══════════════════════════════════════════════════════════════════
# CONTENT INDEXING (Phase 3)
# ══════════════════════════════════════════════════════════════════

def index_course_content(course_id: int = None) -> int:
    """
    Indexes course descriptions and material titles into content_index.
    Pass course_id to re-index one course, or None to re-index all.
    Returns the number of chunks written.
    Call this after adding/editing courses or materials.
    """
    conn = get_db()
    c    = conn.cursor()

    if course_id:
        c.execute("DELETE FROM content_index WHERE course_id=?", (course_id,))
        c.execute("SELECT id, course_code, course_title, description FROM courses WHERE id=?",
                  (course_id,))
    else:
        c.execute("DELETE FROM content_index")
        c.execute("SELECT id, course_code, course_title, description FROM courses")

    courses = c.fetchall()
    indexed = 0

    for course in courses:
        cid = course["id"]
        tag = f"{course['course_code']} – {course['course_title']}"

        # Course description chunk
        if course["description"]:
            c.execute("""INSERT INTO content_index
                         (course_id, material_id, content_type, content_chunk)
                         VALUES (?, NULL, 'course_description', ?)""",
                      (cid, f"{tag}: {course['description']}"))
            indexed += 1

        # One chunk per material (title + description if available)
        c.execute("""SELECT id, title, file_type,
                            CASE WHEN description IS NOT NULL THEN description ELSE '' END AS description
                     FROM materials WHERE course_id=?""", (cid,))
        for mat in c.fetchall():
            parts = [f"{tag} — {mat['title']}"]
            if mat["description"]:
                parts.append(mat["description"])
            c.execute("""INSERT INTO content_index
                         (course_id, material_id, content_type, content_chunk)
                         VALUES (?, ?, ?, ?)""",
                      (cid, mat["id"], f"material_{mat['file_type']}", " | ".join(parts)))
            indexed += 1

    conn.commit()
    conn.close()
    return indexed


@study_director_bp.route("/api/admin/study-director/index", methods=["POST"])
def trigger_index():
    if not is_admin(session.get("user_id")):
        return jsonify({"error": "Unauthorized"}), 403
    data  = request.get_json() or {}
    count = index_course_content(data.get("course_id"))
    return jsonify({"indexed": count, "message": f"Indexed {count} content chunks"}), 200


# ══════════════════════════════════════════════════════════════════
# TIP LIBRARY — CRUD (Phase 4)
# ══════════════════════════════════════════════════════════════════

@study_director_bp.route("/api/admin/study-director/tips", methods=["GET"])
def list_tips():
    if not is_admin(session.get("user_id")):
        return jsonify({"error": "Unauthorized"}), 403
    conn = get_db()
    c    = conn.cursor()
    c.execute("""SELECT t.*, co.course_code, co.course_title
                 FROM study_tips t
                 LEFT JOIN courses co ON t.course_id=co.id
                 ORDER BY t.created_at DESC""")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(rows), 200


@study_director_bp.route("/api/admin/study-director/tips", methods=["POST"])
def create_tip():
    user_id = session.get("user_id")
    if not is_admin(user_id):
        return jsonify({"error": "Unauthorized"}), 403
    data     = request.get_json() or {}
    body     = (data.get("body") or "").strip()
    category = (data.get("category") or "").strip()
    if not body or not category:
        return jsonify({"error": "Body and category are required"}), 400
    conn = get_db()
    c    = conn.cursor()
    c.execute("""INSERT INTO study_tips
                 (title, body, category, tip_type, course_id, level, semester,
                  department, source_notes, is_ai_generated, is_active, created_by)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?)""",
              (data.get("title"), body, category, data.get("tip_type"),
               data.get("course_id"), data.get("level"), data.get("semester"),
               data.get("department"), data.get("source_notes"), user_id))
    conn.commit()
    tip_id = c.lastrowid
    conn.close()
    return jsonify({"id": tip_id, "message": "Tip created"}), 201


@study_director_bp.route("/api/admin/study-director/tips/<int:tip_id>", methods=["PATCH"])
def update_tip(tip_id):
    if not is_admin(session.get("user_id")):
        return jsonify({"error": "Unauthorized"}), 403
    data    = request.get_json() or {}
    allowed = ["title", "body", "category", "tip_type", "course_id",
               "level", "semester", "department", "source_notes", "is_active"]
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"error": "Nothing to update"}), 400
    conn = get_db()
    c    = conn.cursor()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    c.execute(f"UPDATE study_tips SET {set_clause} WHERE id=?",
              list(updates.values()) + [tip_id])
    conn.commit()
    conn.close()
    return jsonify({"message": "Tip updated"}), 200


@study_director_bp.route("/api/admin/study-director/tips/<int:tip_id>", methods=["DELETE"])
def delete_tip(tip_id):
    if not is_admin(session.get("user_id")):
        return jsonify({"error": "Unauthorized"}), 403
    conn = get_db()
    c    = conn.cursor()
    c.execute("DELETE FROM study_tips WHERE id=?", (tip_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Tip deleted"}), 200


# ══════════════════════════════════════════════════════════════════
# ADMIN — SUBSCRIBERS
# ══════════════════════════════════════════════════════════════════

@study_director_bp.route("/admin/study-director")
def admin_study_director_page():
    if not is_admin(session.get("user_id")):
        return redirect("/login-page")
    return render_template("admin/study_director.html")


@study_director_bp.route("/api/admin/study-director/subscribers")
def list_subscribers():
    if not is_admin(session.get("user_id")):
        return jsonify({"error": "Unauthorized"}), 403
    conn = get_db()
    c    = conn.cursor()
    c.execute("""SELECT id, name, department, level, semester,
                        substr(whatsapp,1,5)||'*****'||substr(whatsapp,-3) AS phone,
                        consent_at, opted_out, opted_out_at, created_at,
                        preferred_categories
                 FROM study_tips_subscribers
                 ORDER BY created_at DESC""")
    rows = []
    for r in c.fetchall():
        row = dict(r)
        try:
            row["preferred_categories"] = json.loads(row["preferred_categories"] or "[]")
        except Exception:
            row["preferred_categories"] = []
        rows.append(row)
    conn.close()
    return jsonify(rows), 200


@study_director_bp.route("/api/admin/study-director/context/<int:subscriber_id>")
def get_subscriber_context(subscriber_id):
    if not is_admin(session.get("user_id")):
        return jsonify({"error": "Unauthorized"}), 403
    ctx = build_student_context(subscriber_id)
    if not ctx:
        return jsonify({"error": "Not found or opted out"}), 404
    # Mask phone in response
    ctx.pop("whatsapp", None)
    return jsonify(ctx), 200


# ══════════════════════════════════════════════════════════════════
# ADMIN — QUEUE & SEND
# ══════════════════════════════════════════════════════════════════

@study_director_bp.route("/api/admin/study-director/queue", methods=["POST"])
def queue_tip():
    """
    Admin selects a tip + subscriber and queues the message.
    Phase 1 (ManualProvider): stores with status='queued', admin sends manually.
    Phase 2 (MetaCloudProvider): fires the API and updates status accordingly.
    """
    if not is_admin(session.get("user_id")):
        return jsonify({"error": "Unauthorized"}), 403
    data          = request.get_json() or {}
    tip_id        = data.get("tip_id")
    subscriber_id = data.get("subscriber_id")
    if not tip_id or not subscriber_id:
        return jsonify({"error": "tip_id and subscriber_id required"}), 400

    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT * FROM study_tips WHERE id=? AND is_active=1", (tip_id,))
    tip = c.fetchone()
    c.execute("SELECT * FROM study_tips_subscribers WHERE id=? AND opted_out=0",
              (subscriber_id,))
    sub = c.fetchone()
    if not tip or not sub:
        conn.close()
        return jsonify({"error": "Tip or subscriber not found"}), 404

    # Insert record first
    c.execute("""INSERT INTO study_director_messages
                 (subscriber_id, tip_id, category, course_id,
                  whatsapp_number, message_body, status)
                 VALUES (?, ?, ?, ?, ?, ?, 'queued')""",
              (subscriber_id, tip_id, tip["category"],
               tip["course_id"], sub["whatsapp"], tip["body"]))
    conn.commit()
    msg_id = c.lastrowid

    # Attempt delivery
    result         = get_provider().send(sub["whatsapp"], tip["body"])
    status         = result.get("status", "queued")
    provider_msg   = result.get("provider_message_id")
    failure_reason = result.get("failure_reason")
    sent_at        = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if status == "sent" else None

    c.execute("""UPDATE study_director_messages
                 SET status=?, provider_message_id=?, failure_reason=?, sent_at=?
                 WHERE id=?""",
              (status, provider_msg, failure_reason, sent_at, msg_id))
    conn.commit()
    conn.close()

    note = ("Message queued. Open WhatsApp Business App and send it manually."
            if status == "queued" else "Message sent via API.")
    return jsonify({"message_id": msg_id, "status": status, "note": note}), 200


@study_director_bp.route("/api/admin/study-director/messages")
def list_messages():
    if not is_admin(session.get("user_id")):
        return jsonify({"error": "Unauthorized"}), 403
    conn = get_db()
    c    = conn.cursor()
    c.execute("""SELECT m.id, m.category, m.message_body, m.status,
                        m.queued_at, m.sent_at, m.failure_reason, m.retry_count,
                        s.name AS subscriber_name,
                        substr(m.whatsapp_number,1,5)||'*****'||substr(m.whatsapp_number,-3) AS phone,
                        t.title AS tip_title
                 FROM study_director_messages m
                 LEFT JOIN study_tips_subscribers s ON m.subscriber_id=s.id
                 LEFT JOIN study_tips t ON m.tip_id=t.id
                 ORDER BY m.queued_at DESC LIMIT 100""")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(rows), 200


# ══════════════════════════════════════════════════════════════════
# ADMIN — STATS
# ══════════════════════════════════════════════════════════════════

@study_director_bp.route("/api/admin/study-director/stats")
def director_stats():
    if not is_admin(session.get("user_id")):
        return jsonify({"error": "Unauthorized"}), 403
    conn = get_db()
    c    = conn.cursor()

    def count(sql, params=()):
        c.execute(sql, params)
        return c.fetchone()[0]

    stats = {
        "active_subscribers": count("SELECT COUNT(*) FROM study_tips_subscribers WHERE opted_out=0"),
        "opted_out":          count("SELECT COUNT(*) FROM study_tips_subscribers WHERE opted_out=1"),
        "active_tips":        count("SELECT COUNT(*) FROM study_tips WHERE is_active=1"),
        "queued_messages":    count("SELECT COUNT(*) FROM study_director_messages WHERE status='queued'"),
        "sent_messages":      count("SELECT COUNT(*) FROM study_director_messages WHERE status IN ('sent','delivered','read')"),
        "failed_messages":    count("SELECT COUNT(*) FROM study_director_messages WHERE status='failed'"),
        "indexed_chunks":     count("SELECT COUNT(*) FROM content_index"),
    }
    conn.close()
    return jsonify(stats), 200
