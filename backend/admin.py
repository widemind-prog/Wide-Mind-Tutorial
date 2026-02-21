from flask import Blueprint, render_template, jsonify, session, redirect, request, abort, flash, send_file, url_for, current_app
from extensions import socketio
from state import online_users
from backend.db import get_db, is_admin
from functools import wraps
from pywebpush import webpush
import json
import os
from werkzeug.utils import secure_filename
from backend.email_service import send_email
admin_bp = Blueprint("admin_bp", __name__, url_prefix="/admin")
# ---------------------
# ADMIN GUARD
# ---------------------
def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session or not is_admin(session["user_id"]):
            return redirect("/login-page")
        return func(*args, **kwargs)
    return wrapper

# ---------------------
# DASHBOARD
# ---------------------
@admin_bp.route("/")
@admin_required
def dashboard():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS unread FROM contact_messages WHERE is_read = 0")
    unread = c.fetchone()["unread"]
    conn.close()
    return render_template("admin/dashboard.html", unread=unread)

# ---------------------
# NOTIFICATIONS MANAGEMENT
# ---------------------

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

    # ---------------------
    # DETERMINE TARGET USERS
    # ---------------------
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

    # ---------------------
    # PROCESS EACH USER
    # ---------------------
    for user in users:

        uid = int(user["id"])
        email = user["email"]

        # 1️⃣ Save notification in DB
        c.execute("""
            INSERT INTO notifications (user_id, title, message, link, is_critical)
            VALUES (?, ?, ?, ?, ?)
        """, (uid, title, message, link, int(is_critical)))

        # 2️⃣ Real-time WebSocket
        socketio.emit(
            "new_notification",
            {
                "title": title,
                "message": message,
                "link": link
            },
            room=f"user_{uid}"
        )

        # 3️⃣ Push Notification (always attempt)
        try:
            send_push(uid, title, message, link)
        except Exception as e:
            print("Push error:", e)

        # 4️⃣ EMAIL FALLBACK LOGIC
        # Send email if:
        # - user is offline
        # - OR notification is marked critical

        is_offline = uid not in online_users

        if email and (is_offline or is_critical):
            try:
                send_email(
                    to_email=email,
                    subject=title,
                    body=message
                )
                print(f"Email sent to {email}")
            except Exception as e:
                print(f"Email failed for {email}:", e)

    conn.commit()
    conn.close()

    flash("Notification sent successfully", "success")
    return redirect(url_for("admin_bp.notifications_page"))


# ---------------------
# PUSH DELIVERY
# ---------------------

def send_push(user_id, title, message, link):

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM push_subscriptions WHERE user_id=?", (user_id,))
    subs = c.fetchall()
    conn.close()

    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {
                        "p256dh": sub["p256dh"],
                        "auth": sub["auth"]
                    }
                },
                data=json.dumps({
                    "title": title,
                    "message": message,
                    "link": link
                }),
                vapid_private_key=os.environ.get("VAPID_PRIVATE_KEY"),
                vapid_claims={
                    "sub": "mailto:wideminddevs@gmail.com"
                }
            )
        except Exception as e:
            print("Push failed:", e)
            
# ---------------------
# MESSAGES MANAGEMENT
# ---------------------
@admin_bp.route("/messages")
@admin_required
def messages():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, name, email, subject, message, created_at, is_read
        FROM contact_messages
        ORDER BY created_at DESC
    """)
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

# ---------------------
# USERS MANAGEMENT
# ---------------------
@admin_bp.route("/users")
@admin_required
def users():
    conn = get_db()
    c = conn.cursor()

    # ---- USER STATS ----
    c.execute("SELECT COUNT(*) AS total FROM users")
    total_users = c.fetchone()["total"]

    c.execute("""
        SELECT COUNT(DISTINCT u.id) AS paid
        FROM users u
        JOIN payments p ON u.id = p.user_id
        WHERE COALESCE(p.admin_override_status, p.status) = 'paid'
    """)
    paid_users = c.fetchone()["paid"]

    c.execute("SELECT COUNT(*) AS suspended FROM users WHERE is_suspended = 1")
    suspended_users = c.fetchone()["suspended"]

    unpaid_users = total_users - paid_users

    # ---- USER LIST ----
    c.execute("""
        SELECT
            u.id,
            u.name,
            u.email,
            u.level,
            u.role,
            u.is_suspended,
            COALESCE(p.admin_override_status, p.status) AS payment_status
        FROM users u
        LEFT JOIN payments p ON u.id = p.user_id
        ORDER BY u.id DESC
    """)
    users = c.fetchall()

    conn.close()

    return render_template(
        "admin/users.html",
        users=users,
        total_users=total_users,
        paid_users=paid_users,
        unpaid_users=unpaid_users,
        suspended_users=suspended_users
    )

@admin_bp.route("/users/suspend/<int:user_id>", methods=["POST"])
@admin_required
def toggle_suspend_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET is_suspended = CASE WHEN is_suspended = 1 THEN 0 ELSE 1 END
        WHERE id = ?
    """, (user_id,))
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
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    flash("User deleted", "success")
    return redirect(url_for("admin_bp.users"))

# ---------------------
# TOGGLE PAYMENT (FIXED)
# ---------------------
@admin_bp.route("/users/mark-paid/<int:user_id>", methods=["POST"])
@admin_required
def toggle_payment(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    if not user or user["role"] == "admin":
        conn.close()
        flash("Cannot modify admin payment", "error")
        return redirect(url_for("admin_bp.users"))

    c.execute("""
        SELECT id, status, admin_override_status
        FROM payments
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 1
    """, (user_id,))
    payment = c.fetchone()

    if not payment:
        c.execute("""
            INSERT INTO payments (user_id, amount, status, admin_override_status, paid_at)
            VALUES (?, ?, 'unpaid', 'paid', datetime('now'))
        """, (user_id, 2000000))
        new_status = "paid"
    else:
        current = payment["admin_override_status"] if payment["admin_override_status"] else payment["status"]
        new_status = "unpaid" if current == "paid" else "paid"
        c.execute("""
            UPDATE payments
            SET admin_override_status=?, paid_at=datetime('now')
            WHERE id=?
        """, (new_status, payment["id"]))

    conn.commit()
    conn.close()
    flash(f"Payment marked as {new_status}", "success")
    return redirect(url_for("admin_bp.users"))

# ---------------------
# COURSES MANAGEMENT
# ---------------------
@admin_bp.route("/courses")
@admin_required
def courses():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM courses ORDER BY id DESC")
    courses = c.fetchall()
    conn.close()
    return render_template("admin/courses.html", courses=courses)

@admin_bp.route("/courses/add", methods=["POST"])
@admin_required
def add_course():
    course_code = request.form.get("course_code", "").strip()
    course_title = request.form.get("course_title", "").strip()
    description = request.form.get("description", "").strip()
    if not course_code or not course_title:
        flash("Course code and title are required.", "error")
        return redirect(url_for("admin_bp.courses"))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM courses WHERE course_code = ?", (course_code,))
    if c.fetchone():
        conn.close()
        flash(f"Course code '{course_code}' already exists.", "error")
        return redirect(url_for("admin_bp.courses"))
    c.execute("INSERT INTO courses (course_code, course_title, description) VALUES (?, ?, ?)", (course_code, course_title, description))
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
        if not course_code or not course_title:
            flash("Course code and title are required.", "error")
            return redirect(f"/admin/courses/edit/{course_id}")
        c.execute("SELECT id FROM courses WHERE course_code=? AND id != ?", (course_code, course_id))
        if c.fetchone():
            flash(f"Course code '{course_code}' already exists.", "error")
            return redirect(f"/admin/courses/edit/{course_id}")
        c.execute("UPDATE courses SET course_code=?, course_title=?, description=? WHERE id=?", 
                  (course_code, course_title, description, course_id))
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

# ---------------------
# MATERIALS MANAGEMENT
# ---------------------
@admin_bp.route("/courses/material/add/<file_type>/<int:course_id>", methods=["POST"])
@admin_required
def add_material(file_type, course_id):
    file = request.files.get(file_type)
    title = request.form.get("title")
    if not file or not title or title.strip() == "":
        return "Error: File and title are required.", 400
    filename = secure_filename(file.filename)
    if filename == "":
        return "Error: Invalid file name.", 400
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM materials WHERE course_id=? AND filename=?", (course_id, filename))
    if c.fetchone():
        conn.close()
        return f"Error: Material '{filename}' already exists for this course.", 400
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))
    c.execute("INSERT INTO materials (course_id, filename, file_type, title) VALUES (?, ?, ?, ?)", 
              (course_id, filename, file_type, title))
    conn.commit()
    conn.close()
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
    filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], material["filename"])
    if os.path.exists(filepath):
        os.remove(filepath)
    c.execute("DELETE FROM materials WHERE id=?", (material_id,))
    conn.commit()
    conn.close()
    return redirect(f"/admin/courses/edit/{material['course_id']}")