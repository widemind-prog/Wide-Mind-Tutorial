from flask import Blueprint, render_template, jsonify, session, redirect, request, abort, flash, url_for, current_app
from extensions import socketio
from state import online_users
from backend.db import get_db, is_admin
from functools import wraps
from pywebpush import webpush
import json
import os
from werkzeug.utils import secure_filename
from backend.email_service import send_email, send_new_material_email

admin_bp = Blueprint("admin_bp", __name__, url_prefix="/admin")

LEVEL_AMOUNTS = {
    "300": 1026375,
    "400": 1533042,
    "500": 2041025,
}

def get_amount_for_level(level):
    return LEVEL_AMOUNTS.get(str(level), 1026375)

def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session or not is_admin(session["user_id"]):
            return redirect("/login-page")
        return func(*args, **kwargs)
    return wrapper

# =====================
# DASHBOARD
# =====================
@admin_bp.route("/")
@admin_required
def dashboard():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS unread FROM contact_messages WHERE is_read = 0")
    unread = c.fetchone()["unread"]
    conn.close()
    return render_template("admin/dashboard.html", unread=unread)

@admin_bp.route("/api/subscribe", methods=["POST"])
def subscribe():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO push_subscriptions (user_id, endpoint, p256dh, auth)
        VALUES (?, ?, ?, ?)
    """, (session["user_id"], data["endpoint"], data["keys"]["p256dh"], data["keys"]["auth"]))
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
    c = conn.cursor()
    c.execute("SELECT id, name, email FROM users WHERE role != 'admin'")
    users = c.fetchall()
    conn.close()
    return render_template("admin/send_notification.html", users=users)

@admin_bp.route("/notifications/send", methods=["POST"])
@admin_required
def send_notification():
    send_all = request.form.get("send_all")
    user_id = request.form.get("user_id")
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
        c.execute("SELECT id, email FROM users WHERE role != 'admin'")
        users = c.fetchall()
    else:
        if not user_id:
            flash("Select a user or choose send to all", "error")
            conn.close()
            return redirect(url_for("admin_bp.notifications_page"))
        c.execute("SELECT id, email FROM users WHERE id=?", (user_id,))
        users = c.fetchall()

    for user in users:
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
    flash("Notification sent successfully", "success")
    return redirect(url_for("admin_bp.notifications_page"))

def send_push(user_id, title, message, link):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM push_subscriptions WHERE user_id=?", (user_id,))
    subs = c.fetchall()
    conn.close()
    for sub in subs:
        try:
            private_key = os.environ.get("VAPID_PRIVATE_KEY")
            webpush(
                subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=json.dumps({"title": title, "message": message, "link": link}),
                vapid_private_key=private_key,
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
    c.execute("UPDATE contact_messages SET is_read = 1 WHERE id = ?", (msg_id,))
    conn.commit()
    conn.close()
    flash("Message marked as read", "success")
    return redirect(url_for("admin_bp.messages"))

@admin_bp.route("/messages/unread/<int:msg_id>", methods=["POST"])
@admin_required
def mark_message_unread(msg_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE contact_messages SET is_read = 0 WHERE id = ?", (msg_id,))
    conn.commit()
    conn.close()
    flash("Message marked as unread", "success")
    return redirect(url_for("admin_bp.messages"))

@admin_bp.route("/messages/delete/<int:msg_id>", methods=["POST"])
@admin_required
def delete_message(msg_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM contact_messages WHERE id = ?", (msg_id,))
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
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS total FROM users")
    total_users = c.fetchone()["total"]
    c.execute("""
        SELECT COUNT(DISTINCT u.id) AS paid FROM users u
        JOIN payments p ON u.id = p.user_id
        WHERE COALESCE(p.admin_override_status, p.status) = 'paid'
    """)
    paid_users = c.fetchone()["paid"]
    c.execute("SELECT COUNT(*) AS suspended FROM users WHERE is_suspended = 1")
    suspended_users = c.fetchone()["suspended"]
    unpaid_users = total_users - paid_users
    c.execute("""
        SELECT u.id, u.name, u.email, u.level, u.semester, u.role, u.is_suspended,
               COALESCE(p.admin_override_status, p.status) AS payment_status,
               p.amount
        FROM users u
        LEFT JOIN payments p ON u.id = p.user_id
        ORDER BY u.id DESC
    """)
    users = c.fetchall()
    conn.close()
    return render_template("admin/users.html", users=users,
                           total_users=total_users, paid_users=paid_users,
                           unpaid_users=unpaid_users, suspended_users=suspended_users)

@admin_bp.route("/users/suspend/<int:user_id>", methods=["POST"])
@admin_required
def toggle_suspend_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET is_suspended = CASE WHEN is_suspended = 1 THEN 0 ELSE 1 END WHERE id = ?", (user_id,))
    conn.commit()
    c.execute("SELECT is_suspended FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    flash("User has been suspended" if user["is_suspended"] else "User has been unsuspended", "success")
    return redirect(url_for("admin_bp.users"))

@admin_bp.route("/users/delete/<int:user_id>", methods=["POST"])
@admin_required
def delete_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM payments WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM notifications WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM push_subscriptions WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM password_resets WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    flash("User deleted", "success")
    return redirect(url_for("admin_bp.users"))

# =====================
# EDIT USER LEVEL/SEMESTER
# =====================
@admin_bp.route("/users/edit-level/<int:user_id>", methods=["POST"])
@admin_required
def edit_user_level(user_id):
    level = request.form.get("level", "").strip()
    semester = request.form.get("semester", "").strip()

    if level not in ("300", "400", "500"):
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

    # Update payment amount for new level, reset to unpaid
    new_amount = get_amount_for_level(level)
    c.execute("""
        UPDATE payments
        SET amount=?, status='unpaid', admin_override_status=NULL, reference=NULL, paid_at=NULL
        WHERE user_id=?
    """, (new_amount, user_id))
    conn.commit()
    conn.close()
    flash(f"User updated to {level}L Semester {semester}. Payment reset to unpaid.", "success")
    return redirect(url_for("admin_bp.users"))

# =====================
# MARK ALL UNPAID
# =====================
@admin_bp.route("/users/mark-all-unpaid", methods=["POST"])
@admin_required
def mark_all_unpaid():
    conn = get_db()
    c = conn.cursor()
    # Reset all non-admin users to unpaid, preserving correct amount per level
    c.execute("""
        SELECT u.id, u.level FROM users u WHERE u.role != 'admin'
    """)
    users = c.fetchall()
    for user in users:
        new_amount = get_amount_for_level(user["level"])
        c.execute("""
            UPDATE payments
            SET status='unpaid', admin_override_status=NULL, reference=NULL, paid_at=NULL, amount=?
            WHERE user_id=?
        """, (new_amount, user["id"]))
    conn.commit()
    conn.close()
    flash(f"All {len(users)} students marked as unpaid.", "success")
    return redirect(url_for("admin_bp.users"))

# =====================
# BULK MIGRATION
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
        # Get affected users first
        c.execute("SELECT id FROM users WHERE level='400' AND semester=2 AND role!='admin'")
        affected_users = c.fetchall()
        count = len(affected_users)

        # Update level
        c.execute("UPDATE users SET level='500', semester=2 WHERE level='400' AND semester=2 AND role!='admin'")

        # Reset payments to unpaid with new 500L amount
        new_amount = get_amount_for_level("500")
        for user in affected_users:
            c.execute("""
                UPDATE payments
                SET amount=?, status='unpaid', admin_override_status=NULL, reference=NULL, paid_at=NULL
                WHERE user_id=?
            """, (new_amount, user["id"]))

        conn.commit()
        conn.close()
        flash(f"Migration complete: {count} students moved to 500L (2nd Semester). All payment reset to unpaid.", "success")

    elif action == "custom":
        from_level = request.form.get("from_level", "").strip()
        from_sem = request.form.get("from_semester", "").strip()
        to_level = request.form.get("to_level", "").strip()
        to_sem = request.form.get("to_semester", "").strip()

        if from_level not in ("300", "400", "500") or to_level not in ("300", "400", "500"):
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

        # Get affected users
        c.execute("SELECT id FROM users WHERE level=? AND semester=? AND role!='admin'", (from_level, from_sem))
        affected_users = c.fetchall()
        count = len(affected_users)

        c.execute("UPDATE users SET level=?, semester=? WHERE level=? AND semester=? AND role!='admin'",
                  (to_level, to_sem, from_level, from_sem))

        new_amount = get_amount_for_level(to_level)
        for user in affected_users:
            c.execute("""
                UPDATE payments
                SET amount=?, status='unpaid', admin_override_status=NULL, reference=NULL, paid_at=NULL
                WHERE user_id=?
            """, (new_amount, user["id"]))

        conn.commit()
        conn.close()
        flash(f"Migration complete: {count} students moved from {from_level}L S{from_sem} → {to_level}L S{to_sem}. All payment reset to unpaid.", "success")

    else:
        conn.close()
        flash("Unknown action", "error")

    return redirect(url_for("admin_bp.migration_page"))

# =====================
# TOGGLE PAYMENT
# =====================
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
    amount = get_amount_for_level(user["level"])

    if not payment:
        c.execute("INSERT INTO payments (user_id, amount, status, admin_override_status, paid_at) VALUES (?, ?, 'unpaid', 'paid', datetime('now'))",
                  (user_id, amount))
        new_status = "paid"
    else:
        current = payment["admin_override_status"] if payment["admin_override_status"] else payment["status"]
        new_status = "unpaid" if current == "paid" else "paid"
        c.execute("UPDATE payments SET admin_override_status=?, paid_at=datetime('now') WHERE id=?",
                  (new_status, payment["id"]))

    conn.commit()
    conn.close()
    flash(f"Payment marked as {new_status}", "success")
    return redirect(url_for("admin_bp.users"))

# =====================
# USER FILTER PAGES
# =====================
def get_user_list(filter_type):
    conn = get_db()
    c = conn.cursor()
    base_query = """
        SELECT u.id, u.name, u.email, u.level, u.semester, u.role, u.is_suspended,
               COALESCE(p.admin_override_status, p.status) AS payment_status, p.amount
        FROM users u
        LEFT JOIN payments p ON u.id = p.user_id
        WHERE u.role != 'admin'
    """
    if filter_type == "paid":
        c.execute(base_query + " AND COALESCE(p.admin_override_status, p.status) = 'paid' ORDER BY u.id DESC")
    elif filter_type == "unpaid":
        c.execute(base_query + " AND (COALESCE(p.admin_override_status, p.status) != 'paid' OR p.id IS NULL) ORDER BY u.id DESC")
    elif filter_type == "suspended":
        c.execute(base_query + " AND u.is_suspended = 1 ORDER BY u.id DESC")
    else:
        c.execute(base_query + " ORDER BY u.id DESC")
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
# COURSES
# =====================
@admin_bp.route("/courses")
@admin_required
def courses():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM courses ORDER BY level ASC, semester ASC, id DESC")
    courses = c.fetchall()
    conn.close()
    return render_template("admin/courses.html", courses=courses)

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
    if level not in ("300", "400", "500"):
        flash("Invalid level selected.", "error")
        return redirect(url_for("admin_bp.courses"))
    try:
        semester = int(semester)
        if semester not in (1, 2):
            raise ValueError
    except (ValueError, TypeError):
        flash("Invalid semester selected.", "error")
        return redirect(url_for("admin_bp.courses"))

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM courses WHERE course_code=? AND level=? AND semester=?", (course_code, level, semester))
    if c.fetchone():
        conn.close()
        flash(f"Course '{course_code}' already exists for {level}L Semester {semester}.", "error")
        return redirect(url_for("admin_bp.courses"))

    c.execute("INSERT INTO courses (course_code, course_title, description, level, semester) VALUES (?, ?, ?, ?, ?)",
              (course_code, course_title, description, level, semester))
    conn.commit()
    conn.close()
    flash("Course added successfully!", "success")
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
            flash("Course code and title are required.", "error")
            return redirect(f"/admin/courses/edit/{course_id}")
        if level not in ("300", "400", "500"):
            flash("Invalid level.", "error")
            return redirect(f"/admin/courses/edit/{course_id}")
        try:
            semester = int(semester)
            if semester not in (1, 2):
                raise ValueError
        except (ValueError, TypeError):
            flash("Invalid semester.", "error")
            return redirect(f"/admin/courses/edit/{course_id}")

        c.execute("SELECT id FROM courses WHERE course_code=? AND level=? AND semester=? AND id != ?",
                  (course_code, level, semester, course_id))
        if c.fetchone():
            flash(f"Course '{course_code}' already exists for {level}L Semester {semester}.", "error")
            return redirect(f"/admin/courses/edit/{course_id}")

        c.execute("UPDATE courses SET course_code=?, course_title=?, description=?, level=?, semester=? WHERE id=?",
                  (course_code, course_title, description, level, semester, course_id))
        conn.commit()
        flash("Course updated successfully!", "success")

    c.execute("SELECT * FROM courses WHERE id=?", (course_id,))
    course = c.fetchone()
    c.execute("SELECT id, filename, file_type, title FROM materials WHERE course_id=?", (course_id,))
    materials = c.fetchall()
    conn.close()
    return render_template("admin/edit_course.html", course=course, materials=materials)

@admin_bp.route("/courses/delete/<int:course_id>", methods=["POST"])
@admin_required
def delete_course(course_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM courses WHERE id=?", (course_id,))
    conn.commit()
    conn.close()
    flash("Course deleted", "success")
    return redirect(url_for("admin_bp.courses"))

# =====================
# MATERIALS
# =====================
@admin_bp.route("/courses/material/add/<file_type>/<int:course_id>", methods=["POST"])
@admin_required
def add_material(file_type, course_id):
    title = request.form.get("title", "").strip()
    file = request.files.get("file")

    if not title or not file or file.filename == "":
        flash("Title and file are required.", "error")
        return redirect(f"/admin/courses/edit/{course_id}")

    filename = secure_filename(file.filename)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM materials WHERE course_id=? AND filename=?", (course_id, filename))
    if c.fetchone():
        conn.close()
        flash("A material with that filename already exists for this course.", "error")
        return redirect(f"/admin/courses/edit/{course_id}")

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    bucket = "materials"
    file_bytes = file.read()
    content_type = "application/pdf" if file_type == "pdf" else "audio/mpeg"

    upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{filename}"
    headers = {"Authorization": f"Bearer {supabase_key}", "Content-Type": content_type, "x-upsert": "true"}

    import requests as req
    response = req.post(upload_url, headers=headers, data=file_bytes)
    if response.status_code not in (200, 201):
        flash(f"Upload to Supabase failed: {response.text}", "error")
        conn.close()
        return redirect(f"/admin/courses/edit/{course_id}")

    file_url = f"{supabase_url}/storage/v1/object/public/{bucket}/{filename}"
    c.execute("INSERT INTO materials (course_id, filename, file_type, title, file_url) VALUES (?, ?, ?, ?, ?)",
              (course_id, filename, file_type, title, file_url))
    conn.commit()
    conn.close()

    try:
        conn2 = get_db()
        c2 = conn2.cursor()
        c2.execute("SELECT * FROM courses WHERE id=?", (course_id,))
        course = c2.fetchone()
        c2.execute("""
            SELECT u.name, u.email FROM users u
            JOIN payments p ON u.id = p.user_id
            WHERE u.role != 'admin'
            AND COALESCE(p.admin_override_status, p.status) = 'paid'
            AND u.level = ? AND u.semester = ?
        """, (course["level"], course["semester"]))
        paid_users = c2.fetchall()
        conn2.close()
        for u in paid_users:
            send_new_material_email(to_email=u["email"], name=u["name"], material_title=title,
                                    course_title=course["course_title"] if course else "your course",
                                    file_type=file_type, course_id=course_id)
    except Exception as e:
        print("New material email failed:", e)

    flash("Material uploaded successfully!", "success")
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

    c.execute("DELETE FROM materials WHERE id=?", (material_id,))
    conn.commit()
    conn.close()
    return redirect(f"/admin/courses/edit/{material['course_id']}")
