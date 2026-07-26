from flask import Blueprint, render_template, jsonify, session, redirect, request, abort, flash, url_for
from extensions import socketio
from backend.db import get_db, is_admin
from functools import wraps
from pywebpush import webpush
import json, os
from werkzeug.utils import secure_filename
from backend.email_service import send_email, send_new_material_email

admin_bp = Blueprint("admin_bp", __name__, url_prefix="/admin")

LEVEL_AMOUNTS = {
    "100": 1035750,
    "200": 1343500,
    "300": 1548500,
    "400": 1856000,
    "500": 2061000,
}
RERUN_AMOUNTS = {
    "100": 359231,
    "200": 359231,
    "300": 359231,
    "400": 536565,
}

ALL_LEVELS = ("100", "200", "300", "400", "500")

def get_amount_for_level(level):
    return LEVEL_AMOUNTS.get(str(level), 1035750)

def get_rerun_amount(level):
    return RERUN_AMOUNTS.get(str(level), 359231)

def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session or not is_admin(session["user_id"]):
            return redirect("/login-page")
        return func(*args, **kwargs)
    return wrapper

def _get_all_users(conn):
    c = conn.cursor()
    c.execute("""
        SELECT u.id, u.name, u.email, u.level, u.semester, u.role, u.is_suspended,
               COALESCE(p.admin_override_status, p.status) AS payment_status, p.amount
        FROM users u
        LEFT JOIN payments p ON u.id = p.user_id
        ORDER BY u.id DESC
    """)
    return c.fetchall()

def _get_rerun_by_user(conn):
    c = conn.cursor()
    c.execute("SELECT user_id, rerun_level, COALESCE(admin_override_status, status) AS effective_status FROM rerun_passes")
    passes = c.fetchall()
    result = {}
    for p in passes:
        uid = p["user_id"]
        if uid not in result:
            result[uid] = []
        result[uid].append({"level": p["rerun_level"], "status": p["effective_status"]})
    return result

# =====================
# DASHBOARD
# =====================
@admin_bp.route("/")
@admin_required
def dashboard():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS n FROM contact_messages WHERE is_read=0")
    unread = c.fetchone()["n"]

    level_stats = {}
    for lvl in ALL_LEVELS:
        c.execute("SELECT COUNT(*) AS total FROM users WHERE level=? AND role!='admin'", (lvl,))
        total = c.fetchone()["total"]
        c.execute("""
            SELECT COUNT(DISTINCT u.id) AS paid FROM users u
            JOIN payments p ON u.id=p.user_id
            WHERE u.level=? AND u.role!='admin'
            AND COALESCE(p.admin_override_status, p.status)='paid'
        """, (lvl,))
        paid = c.fetchone()["paid"]
        level_stats[lvl] = {"total": total, "paid": paid, "unpaid": total - paid}

    c.execute("SELECT COUNT(*) AS n FROM rerun_passes WHERE COALESCE(admin_override_status,status)='paid' AND rerun_level='300'")
    rerun_300 = c.fetchone()["n"]
    c.execute("SELECT COUNT(*) AS n FROM rerun_passes WHERE COALESCE(admin_override_status,status)='paid' AND rerun_level='400'")
    rerun_400 = c.fetchone()["n"]

    c.execute("""
        SELECT u.name, u.email, u.level, u.semester,
               COALESCE(p.admin_override_status, p.status) AS payment_status
        FROM users u
        LEFT JOIN payments p ON u.id=p.user_id
        WHERE u.role!='admin'
        ORDER BY u.id DESC LIMIT 5
    """)
    recent_users = c.fetchall()
    conn.close()

    return render_template("admin/dashboard.html",
                           unread=unread,
                           level_stats=level_stats,
                           rerun_300=rerun_300,
                           rerun_400=rerun_400,
                           rerun_total=rerun_300+rerun_400,
                           recent_users=recent_users)

@admin_bp.route("/api/subscribe", methods=["POST"])
def subscribe():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (?, ?, ?, ?)",
              (session["user_id"], data["endpoint"], data["keys"]["p256dh"], data["keys"]["auth"]))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# =====================
# NOTIFICATIONS
# =====================
@admin_bp.route("/notifications")
@admin_required
def notifications_page():
    conn = get_db()
    users = _get_all_users(conn)
    conn.close()
    users_list = [{"id": u["id"], "name": u["name"], "email": u["email"],
                   "level": u["level"], "semester": u["semester"], "role": u["role"]}
                  for u in users]
    return render_template("admin/send_notification.html", users_json=json.dumps(users_list))

@admin_bp.route("/notifications/send", methods=["POST"])
@admin_required
def send_notification():
    send_all = request.form.get("send_all")
    user_id = request.form.get("user_id")
    target_level = request.form.get("target_level", "").strip()
    target_semester = request.form.get("target_semester", "").strip()
    title = request.form.get("title")
    message = request.form.get("message")
    link = request.form.get("link") or "/"
    is_critical = request.form.get("is_critical") == "1"

    if not title or not message:
        flash("Missing title or message", "error")
        return redirect(url_for("admin_bp.notifications_page"))

    conn = get_db()
    c = conn.cursor()

    if send_all:
        c.execute("SELECT id, email FROM users WHERE role!='admin'")
        recipients = c.fetchall()
    elif target_level or target_semester:
        sql = "SELECT id, email FROM users WHERE role!='admin'"
        params = []
        if target_level:
            sql += " AND level=?"
            params.append(target_level)
        if target_semester:
            sql += " AND semester=?"
            params.append(int(target_semester))
        c.execute(sql, params)
        recipients = c.fetchall()
    elif user_id:
        c.execute("SELECT id, email FROM users WHERE id=?", (user_id,))
        recipients = c.fetchall()
    else:
        flash("Select a target", "error")
        conn.close()
        return redirect(url_for("admin_bp.notifications_page"))

    for user in recipients:
        uid = int(user["id"])
        email = user["email"]
        c.execute("INSERT INTO notifications (user_id, title, message, link, is_critical) VALUES (?, ?, ?, ?, ?)",
                  (uid, title, message, link, int(is_critical)))
        socketio.emit("new_notification", {"title": title, "message": message, "link": link}, room=f"user_{uid}")
        try:
            send_push(uid, title, message, link)
        except Exception as e:
            print("Push error:", e)
        if is_critical:
            try:
                send_email(to_email=email, subject=title, body=message)
            except Exception as e:
                print("Email failed:", e)

    conn.commit()
    conn.close()
    flash(f"Notification sent to {len(recipients)} student(s)", "success")
    return redirect(url_for("admin_bp.notifications_page"))

def send_push(user_id, title, message, link):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM push_subscriptions WHERE user_id=?", (user_id,))
    subs = c.fetchall()
    conn.close()
    for sub in subs:
        try:
            webpush(
                subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=json.dumps({"title": title, "message": message, "link": link}),
                vapid_private_key=os.environ.get("VAPID_PRIVATE_KEY"),
                vapid_claims={"sub": "mailto:wideminddevs@gmail.com"}
            )
        except Exception as e:
            print(f"Push failed: {type(e).__name__}: {e}")

# =====================
# MESSAGES
# =====================
@admin_bp.route("/messages")
@admin_required
def messages():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name, email, subject, message, created_at, is_read FROM contact_messages ORDER BY created_at DESC")
    messages = c.fetchall()
    conn.close()
    return render_template("admin/messages.html", messages=messages)

@admin_bp.route("/messages/unread-count")
@admin_required
def unread_messages_count():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS unread FROM contact_messages WHERE is_read=0")
    unread = c.fetchone()["unread"]
    conn.close()
    return jsonify({"unread": unread})

@admin_bp.route("/messages/read/<int:msg_id>", methods=["POST"])
@admin_required
def mark_message_read(msg_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contact_messages SET is_read=1 WHERE id=?", (msg_id,))
    conn.commit()
    conn.close()
    flash("Message marked as read", "success")
    return redirect(url_for("admin_bp.messages"))

@admin_bp.route("/messages/unread/<int:msg_id>", methods=["POST"])
@admin_required
def mark_message_unread(msg_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contact_messages SET is_read=0 WHERE id=?", (msg_id,))
    conn.commit()
    conn.close()
    flash("Message marked as unread", "success")
    return redirect(url_for("admin_bp.messages"))

@admin_bp.route("/messages/delete/<int:msg_id>", methods=["POST"])
@admin_required
def delete_message(msg_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM contact_messages WHERE id=?", (msg_id,))
    conn.commit()
    conn.close()
    flash("Message deleted", "success")
    return redirect(url_for("admin_bp.messages"))

@admin_bp.route("/messages/delete-bulk", methods=["POST"])
@admin_required
def bulk_delete_messages():
    ids = request.form.getlist("message_ids")
    if not ids:
        flash("No messages selected", "error")
        return redirect(url_for("admin_bp.messages"))
    conn = get_db()
    c = conn.cursor()
    placeholders = ",".join("?" for _ in ids)
    c.execute(f"DELETE FROM contact_messages WHERE id IN ({placeholders})", ids)
    conn.commit()
    conn.close()
    flash(f"{len(ids)} message(s) deleted", "success")
    return redirect(url_for("admin_bp.messages"))

# =====================
# USERS
# =====================
@admin_bp.route("/users")
@admin_required
def users():
    conn = get_db()
    all_users = _get_all_users(conn)
    rerun_by_user = _get_rerun_by_user(conn)
    conn.close()

    total_users = sum(1 for u in all_users if u["role"] != "admin")
    paid_users = sum(1 for u in all_users if u["role"] != "admin" and u["payment_status"] == "paid")
    suspended_users = sum(1 for u in all_users if u["is_suspended"])
    unpaid_users = total_users - paid_users

    users_list = []
    for u in all_users:
        users_list.append({
            "id": u["id"], "name": u["name"], "email": u["email"],
            "level": u["level"] or "", "semester": u["semester"] or 2,
            "role": u["role"], "is_suspended": bool(u["is_suspended"]),
            "payment_status": u["payment_status"] or "unpaid",
            "amount": u["amount"] or 0
        })

    rerun_list = {str(k): v for k, v in rerun_by_user.items()}
    return render_template("admin/users.html",
                           users_json=json.dumps(users_list),
                           rerun_json=json.dumps(rerun_list),
                           total_users=total_users,
                           paid_users=paid_users,
                           unpaid_users=unpaid_users,
                           suspended_users=suspended_users)

@admin_bp.route("/users/suspend/<int:user_id>", methods=["POST"])
@admin_required
def toggle_suspend_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET is_suspended=CASE WHEN is_suspended=1 THEN 0 ELSE 1 END WHERE id=?", (user_id,))
    conn.commit()
    c.execute("SELECT is_suspended FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    flash("User suspended" if user["is_suspended"] else "User unsuspended", "success")
    return redirect(url_for("admin_bp.users"))

@admin_bp.route("/users/delete/<int:user_id>", methods=["POST"])
@admin_required
def delete_user(user_id):
    conn = get_db()
    c = conn.cursor()
    for table in ["payments", "rerun_passes", "email_otps", "progress",
                  "notifications", "push_subscriptions", "password_resets"]:
        c.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    flash("User deleted", "success")
    return redirect(url_for("admin_bp.users"))

@admin_bp.route("/users/edit-level/<int:user_id>", methods=["POST"])
@admin_required
def edit_user_level(user_id):
    level = request.form.get("level", "").strip()
    semester = request.form.get("semester", "").strip()
    if level not in ALL_LEVELS:
        flash("Invalid level", "error")
        return redirect(url_for("admin_bp.users"))
    try:
        semester = int(semester)
        if semester not in (1, 2):
            raise ValueError
    except (ValueError, TypeError):
        flash("Invalid semester", "error")
        return redirect(url_for("admin_bp.users"))
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET level=?, semester=? WHERE id=?", (level, semester, user_id))
    new_amount = get_amount_for_level(level)
    c.execute("""UPDATE payments SET amount=?, status='unpaid', admin_override_status=NULL,
                 reference=NULL, paid_at=NULL WHERE user_id=?""", (new_amount, user_id))
    c.execute("DELETE FROM rerun_passes WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    flash(f"Updated to {level}L Semester {semester}. Payment and rerun passes reset.", "success")
    return redirect(url_for("admin_bp.users"))

# =====================
# RESET ALL TRIALS
# =====================
@admin_bp.route("/users/reset-all-trials", methods=["POST"])
@admin_required
def reset_all_trials():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS n FROM users WHERE role!='admin'")
    count = c.fetchone()["n"]
    c.execute("UPDATE users SET trial_started_at=NULL, is_verified=0 WHERE role!='admin'")
    c.execute("DELETE FROM email_otps")
    conn.commit()
    conn.close()
    flash(f"Trial reset complete — {count} students unverified, all OTPs cleared. Trial restarts fresh on next login after TRIAL_ENABLED=true.", "success")
    return redirect(url_for("admin_bp.users"))

@admin_bp.route("/users/mark-all-unpaid", methods=["POST"])
@admin_required
def mark_all_unpaid():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, level FROM users WHERE role!='admin'")
    all_users = c.fetchall()
    for user in all_users:
        new_amount = get_amount_for_level(user["level"])
        c.execute("""UPDATE payments SET status='unpaid', admin_override_status=NULL,
                     reference=NULL, paid_at=NULL, amount=? WHERE user_id=?""", (new_amount, user["id"]))
        c.execute("""UPDATE rerun_passes SET status='unpaid', admin_override_status=NULL,
                     reference=NULL, paid_at=NULL WHERE user_id=?""", (user["id"],))
    conn.commit()
    conn.close()
    flash(f"All {len(all_users)} students marked unpaid.", "success")
    return redirect(url_for("admin_bp.users"))

@admin_bp.route("/users/rerun/toggle/<int:user_id>/<rerun_level>", methods=["POST"])
@admin_required
def toggle_rerun_pass(user_id, rerun_level):
    # Rerun only valid for levels that have a lower level below them
    valid_rerun_levels = ("100", "200", "300", "400")
    if rerun_level not in valid_rerun_levels:
        flash("Invalid rerun level", "error")
        return redirect(url_for("admin_bp.users"))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT level FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    if not user or int(rerun_level) >= int(user["level"]):
        conn.close()
        flash("Rerun level must be below user's level", "error")
        return redirect(url_for("admin_bp.users"))
    c.execute("SELECT id, status, admin_override_status FROM rerun_passes WHERE user_id=? AND rerun_level=?",
              (user_id, rerun_level))
    existing = c.fetchone()
    from datetime import datetime as _dt
    now_str = _dt.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    amount = get_rerun_amount(rerun_level)
    if not existing:
        c.execute("""INSERT INTO rerun_passes (user_id, rerun_level, amount, status, admin_override_status, paid_at)
                     VALUES (?, ?, ?, 'unpaid', 'paid', ?)""", (user_id, rerun_level, amount, now_str))
        new_status = "paid"
    else:
        current = existing["admin_override_status"] if existing["admin_override_status"] else existing["status"]
        new_status = "unpaid" if current == "paid" else "paid"
        c.execute("UPDATE rerun_passes SET admin_override_status=?, paid_at=? WHERE id=?",
                  (new_status, now_str, existing["id"]))
    conn.commit()
    conn.close()
    flash(f"{rerun_level}L rerun pass {'granted' if new_status == 'paid' else 'revoked'}", "success")
    return redirect(url_for("admin_bp.users"))

@admin_bp.route("/users/mark-paid/<int:user_id>", methods=["POST"])
@admin_required
def toggle_payment(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT role, level FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    if not user or user["role"] == "admin":
        conn.close()
        flash("Cannot modify admin payment", "error")
        return redirect(url_for("admin_bp.users"))
    c.execute("SELECT id, status, admin_override_status FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,))
    payment = c.fetchone()
    from datetime import datetime as _dt
    now_str = _dt.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    amount = get_amount_for_level(user["level"])
    if not payment:
        c.execute("INSERT INTO payments (user_id, amount, status, admin_override_status, paid_at) VALUES (?, ?, 'unpaid', 'paid', ?)",
                  (user_id, amount, now_str))
        new_status = "paid"
    else:
        current = payment["admin_override_status"] if payment["admin_override_status"] else payment["status"]
        new_status = "unpaid" if current == "paid" else "paid"
        c.execute("UPDATE payments SET admin_override_status=?, paid_at=? WHERE id=?",
                  (new_status, now_str, payment["id"]))
    conn.commit()
    conn.close()
    flash(f"Payment marked as {new_status}", "success")
    return redirect(url_for("admin_bp.users"))

def get_user_list(filter_type):
    conn = get_db()
    c = conn.cursor()
    base = """SELECT u.id, u.name, u.email, u.level, u.semester, u.role, u.is_suspended,
               COALESCE(p.admin_override_status, p.status) AS payment_status, p.amount
        FROM users u LEFT JOIN payments p ON u.id=p.user_id WHERE u.role!='admin'"""
    if filter_type == "paid":
        c.execute(base + " AND COALESCE(p.admin_override_status, p.status)='paid' ORDER BY u.id DESC")
    elif filter_type == "unpaid":
        c.execute(base + " AND (COALESCE(p.admin_override_status, p.status)!='paid' OR p.id IS NULL) ORDER BY u.id DESC")
    elif filter_type == "suspended":
        c.execute(base + " AND u.is_suspended=1 ORDER BY u.id DESC")
    else:
        c.execute(base + " ORDER BY u.id DESC")
    users = c.fetchall()
    conn.close()
    return users

@admin_bp.route("/users/all")
@admin_required
def users_all():
    return render_template("admin/total.html", users=get_user_list("all"))

@admin_bp.route("/users/paid")
@admin_required
def users_paid():
    return render_template("admin/paid.html", users=get_user_list("paid"))

@admin_bp.route("/users/unpaid")
@admin_required
def users_unpaid():
    return render_template("admin/unpaid.html", users=get_user_list("unpaid"))

@admin_bp.route("/users/suspended")
@admin_required
def users_suspended():
    return render_template("admin/suspended.html", users=get_user_list("suspended"))

# =====================
# MIGRATION
# =====================
@admin_bp.route("/users/migrate")
@admin_required
def migration_page():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS cnt FROM users WHERE level='400' AND semester=2 AND role!='admin'")
    count_400_s2 = c.fetchone()["cnt"]
    conn.close()
    return render_template("admin/migrate.html", count_400_s2=count_400_s2)

@admin_bp.route("/users/migrate", methods=["POST"])
@admin_required
def run_migration():
    action = request.form.get("action")
    conn = get_db()
    c = conn.cursor()
    if action == "promote_400_to_500":
        c.execute("SELECT id FROM users WHERE level='400' AND semester=2 AND role!='admin'")
        affected = c.fetchall()
        count = len(affected)
        c.execute("UPDATE users SET level='500', semester=2 WHERE level='400' AND semester=2 AND role!='admin'")
        new_amount = get_amount_for_level("500")
        for user in affected:
            c.execute("""UPDATE payments SET amount=?, status='unpaid', admin_override_status=NULL,
                         reference=NULL, paid_at=NULL WHERE user_id=?""", (new_amount, user["id"]))
            c.execute("DELETE FROM rerun_passes WHERE user_id=?", (user["id"],))
        conn.commit()
        conn.close()
        flash(f"Migration complete: {count} students → 500L 2nd Semester. Payments reset.", "success")
    elif action == "custom":
        from_level = request.form.get("from_level", "").strip()
        from_sem = request.form.get("from_semester", "").strip()
        to_level = request.form.get("to_level", "").strip()
        to_sem = request.form.get("to_semester", "").strip()
        if from_level not in ALL_LEVELS or to_level not in ALL_LEVELS:
            conn.close()
            flash("Invalid level values", "error")
            return redirect(url_for("admin_bp.migration_page"))
        try:
            from_sem = int(from_sem)
            to_sem = int(to_sem)
            if from_sem not in (1, 2) or to_sem not in (1, 2):
                raise ValueError
        except (ValueError, TypeError):
            conn.close()
            flash("Invalid semester values", "error")
            return redirect(url_for("admin_bp.migration_page"))
        c.execute("SELECT id FROM users WHERE level=? AND semester=? AND role!='admin'", (from_level, from_sem))
        affected = c.fetchall()
        count = len(affected)
        c.execute("UPDATE users SET level=?, semester=? WHERE level=? AND semester=? AND role!='admin'",
                  (to_level, to_sem, from_level, from_sem))
        new_amount = get_amount_for_level(to_level)
        for user in affected:
            c.execute("""UPDATE payments SET amount=?, status='unpaid', admin_override_status=NULL,
                         reference=NULL, paid_at=NULL WHERE user_id=?""", (new_amount, user["id"]))
            c.execute("DELETE FROM rerun_passes WHERE user_id=?", (user["id"],))
        conn.commit()
        conn.close()
        flash(f"Migration complete: {count} students moved. Payments reset.", "success")
    else:
        conn.close()
        flash("Unknown action", "error")
    return redirect(url_for("admin_bp.migration_page"))

# =====================
# COURSES
# =====================
@admin_bp.route("/courses")
@admin_required
def courses():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT co.id, co.course_code, co.course_title, co.description, co.level, co.semester, co.is_trial,
               COUNT(m.id) AS material_count
        FROM courses co
        LEFT JOIN materials m ON m.course_id = co.id
        GROUP BY co.id
        ORDER BY co.level ASC, co.semester ASC, co.id DESC
    """)
    courses = c.fetchall()
    conn.close()
    courses_list = [{
        "id": c["id"], "course_code": c["course_code"], "course_title": c["course_title"],
        "description": c["description"] or "", "level": c["level"],
        "semester": c["semester"], "material_count": c["material_count"],
        "is_trial": bool(c["is_trial"])
    } for c in courses]
    return render_template("admin/courses.html", courses_json=json.dumps(courses_list))

@admin_bp.route("/courses/add", methods=["POST"])
@admin_required
def add_course():
    course_code = request.form.get("course_code", "").strip()
    course_title = request.form.get("course_title", "").strip()
    description = request.form.get("description", "").strip()
    level = request.form.get("level", "").strip()
    semester = request.form.get("semester", "").strip()
    if not course_code or not course_title:
        flash("Course code and title are required.", "error")
        return redirect(url_for("admin_bp.courses"))
    if level not in ALL_LEVELS:
        flash("Invalid level.", "error")
        return redirect(url_for("admin_bp.courses"))
    try:
        semester = int(semester)
        if semester not in (1, 2):
            raise ValueError
    except (ValueError, TypeError):
        flash("Invalid semester.", "error")
        return redirect(url_for("admin_bp.courses"))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM courses WHERE course_code=? AND level=? AND semester=?", (course_code, level, semester))
    if c.fetchone():
        conn.close()
        flash(f"'{course_code}' already exists for {level}L Semester {semester}.", "error")
        return redirect(url_for("admin_bp.courses"))
    c.execute("INSERT INTO courses (course_code, course_title, description, level, semester) VALUES (?, ?, ?, ?, ?)",
              (course_code, course_title, description, level, semester))
    conn.commit()
    conn.close()
    flash("Course added!", "success")
    return redirect(url_for("admin_bp.courses"))

@admin_bp.route("/courses/edit/<int:course_id>", methods=["GET", "POST"])
@admin_required
def edit_course(course_id):
    conn = get_db()
    c = conn.cursor()
    if request.method == "POST":
        course_code = request.form.get("course_code", "").strip()
        course_title = request.form.get("course_title", "").strip()
        description = request.form.get("description", "").strip()
        level = request.form.get("level", "").strip()
        semester = request.form.get("semester", "").strip()
        if not course_code or not course_title:
            flash("Code and title required.", "error")
            return redirect(f"/admin/courses/edit/{course_id}")
        if level not in ALL_LEVELS:
            flash("Invalid level.", "error")
            return redirect(f"/admin/courses/edit/{course_id}")
        try:
            semester = int(semester)
            if semester not in (1, 2):
                raise ValueError
        except (ValueError, TypeError):
            flash("Invalid semester.", "error")
            return redirect(f"/admin/courses/edit/{course_id}")
        c.execute("SELECT id FROM courses WHERE course_code=? AND level=? AND semester=? AND id!=?",
                  (course_code, level, semester, course_id))
        if c.fetchone():
            flash(f"'{course_code}' already exists for {level}L Semester {semester}.", "error")
            return redirect(f"/admin/courses/edit/{course_id}")
        c.execute("UPDATE courses SET course_code=?, course_title=?, description=?, level=?, semester=? WHERE id=?",
                  (course_code, course_title, description, level, semester, course_id))
        conn.commit()
        flash("Course updated!", "success")
    c.execute("SELECT * FROM courses WHERE id=?", (course_id,))
    course = c.fetchone()
    c.execute("SELECT id, filename, file_type, title, duration_seconds FROM materials WHERE course_id=?", (course_id,))
    materials = c.fetchall()
    conn.close()
    return render_template("admin/edit_course.html", course=course, materials=materials)

@admin_bp.route("/courses/delete/<int:course_id>", methods=["POST"])
@admin_required
def delete_course(course_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM progress WHERE material_id IN (SELECT id FROM materials WHERE course_id=?)", (course_id,))
    c.execute("DELETE FROM materials WHERE course_id=?", (course_id,))
    c.execute("DELETE FROM courses WHERE id=?", (course_id,))
    conn.commit()
    conn.close()
    flash("Course deleted", "success")
    return redirect(url_for("admin_bp.courses"))

@admin_bp.route("/courses/set-trial/<int:course_id>", methods=["POST"])
@admin_required
def set_trial_course(course_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, level, semester, is_trial, course_code FROM courses WHERE id=?", (course_id,))
    course = c.fetchone()
    if not course:
        conn.close()
        flash("Course not found", "error")
        return redirect(url_for("admin_bp.courses"))
    if course["is_trial"]:
        c.execute("UPDATE courses SET is_trial=0 WHERE id=?", (course_id,))
        conn.commit()
        conn.close()
        flash(f"'{course['course_code']}' is no longer the trial course.", "success")
    else:
        c.execute("UPDATE courses SET is_trial=0 WHERE level=? AND semester=?",
                  (course["level"], course["semester"]))
        c.execute("UPDATE courses SET is_trial=1 WHERE id=?", (course_id,))
        conn.commit()
        conn.close()
        flash(f"'{course['course_code']}' is now the trial course for {course['level']}L Semester {course['semester']}.", "success")
    return redirect(url_for("admin_bp.courses"))

# =====================
# MATERIALS
# =====================
@admin_bp.route("/courses/material/add/<file_type>/<int:course_id>", methods=["POST"])
@admin_required
def add_material(file_type, course_id):
    title = request.form.get("title", "").strip()
    file = request.files.get("file")
    duration_minutes_raw = request.form.get("duration_minutes", "").strip()
    try:
        duration_seconds = int(round(float(duration_minutes_raw) * 60)) if duration_minutes_raw else 0
    except ValueError:
        duration_seconds = 0
    if not title or not file or file.filename == "":
        flash("Title and file are required.", "error")
        return redirect(f"/admin/courses/edit/{course_id}")
    if duration_seconds <= 0:
        flash("Duration (in minutes) is required and must be greater than 0.", "error")
        return redirect(f"/admin/courses/edit/{course_id}")
    filename = secure_filename(file.filename)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM materials WHERE course_id=? AND filename=?", (course_id, filename))
    if c.fetchone():
        conn.close()
        flash("A material with that filename already exists.", "error")
        return redirect(f"/admin/courses/edit/{course_id}")
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    file_bytes = file.read()
    content_type = "application/pdf" if file_type == "pdf" else "audio/mpeg"
    upload_url = f"{supabase_url}/storage/v1/object/materials/{filename}"
    headers = {"Authorization": f"Bearer {supabase_key}", "Content-Type": content_type, "x-upsert": "true"}
    import requests as req
    response = req.post(upload_url, headers=headers, data=file_bytes)
    if response.status_code not in (200, 201):
        flash(f"Upload failed: {response.text}", "error")
        conn.close()
        return redirect(f"/admin/courses/edit/{course_id}")
    c.execute("INSERT INTO materials (course_id, filename, file_type, title, duration_seconds) VALUES (?, ?, ?, ?, ?)",
              (course_id, filename, file_type, title, duration_seconds))
    conn.commit()
    conn.close()
    try:
        conn2 = get_db()
        c2 = conn2.cursor()
        c2.execute("SELECT * FROM courses WHERE id=?", (course_id,))
        course = c2.fetchone()
        c2.execute("""SELECT u.name, u.email FROM users u JOIN payments p ON u.id=p.user_id
                      WHERE u.role!='admin' AND COALESCE(p.admin_override_status, p.status)='paid'
                      AND u.level=? AND u.semester=?""", (course["level"], course["semester"]))
        paid_users = c2.fetchall()
        conn2.close()
        for u in paid_users:
            send_new_material_email(to_email=u["email"], name=u["name"], material_title=title,
                                    course_title=course["course_title"], file_type=file_type, course_id=course_id)
    except Exception as e:
        print("Email failed:", e)
    flash("Material uploaded!", "success")
    return redirect(f"/admin/courses/edit/{course_id}")

@admin_bp.route("/courses/material/delete/<int:material_id>", methods=["POST"])
@admin_required
def delete_material(material_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT filename, course_id FROM materials WHERE id=?", (material_id,))
    material = c.fetchone()
    if not material:
        conn.close()
        abort(404)
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    if supabase_url and supabase_key:
        import requests as req
        req.delete(f"{supabase_url}/storage/v1/object/materials/{material['filename']}",
                   headers={"Authorization": f"Bearer {supabase_key}"})
    c.execute("DELETE FROM progress WHERE material_id=?", (material_id,))
    c.execute("DELETE FROM materials WHERE id=?", (material_id,))
    conn.commit()
    conn.close()
    return redirect(f"/admin/courses/edit/{material['course_id']}")

@admin_bp.route("/courses/material/edit-duration/<int:material_id>", methods=["POST"])
@admin_required
def edit_material_duration(material_id):
    duration_minutes_raw = request.form.get("duration_minutes", "").strip()
    try:
        duration_seconds = int(round(float(duration_minutes_raw) * 60)) if duration_minutes_raw else 0
    except ValueError:
        duration_seconds = 0
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT course_id FROM materials WHERE id=?", (material_id,))
    material = c.fetchone()
    if not material:
        conn.close()
        abort(404)
    if duration_seconds <= 0:
        conn.close()
        flash("Duration must be greater than 0 minutes.", "error")
        return redirect(f"/admin/courses/edit/{material['course_id']}")
    c.execute("UPDATE materials SET duration_seconds=? WHERE id=?", (duration_seconds, material_id))
    conn.commit()
    conn.close()
    flash("Duration updated.", "success")
    return redirect(f"/admin/courses/edit/{material['course_id']}")
