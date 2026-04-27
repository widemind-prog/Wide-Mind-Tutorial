from flask import Blueprint, render_template, jsonify, session, redirect, request, abort, flash, send_file, url_for, current_app
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

@admin_bp.route("/api/subscribe", methods=["POST"])
def subscribe():

    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    user_id = session["user_id"]
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT OR REPLACE INTO push_subscriptions
        (user_id, endpoint, p256dh, auth)
        VALUES (?, ?, ?, ?)
    """, (
        user_id,
        data["endpoint"],
        data["keys"]["p256dh"],
        data["keys"]["auth"]
    ))

    conn.commit()
    conn.close()

    return jsonify({"success": True})

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

        # 3️⃣ Push Notification
        try:
            send_push(uid, title, message, link)
        except Exception as e:
            print("Push error:", e)

        # 4️⃣ Email ONLY if critical
        if is_critical:
            try:
                send_email(
                    to_email=email,
                    subject=title,
                    body=message
                )
            except Exception as e:
                print("Email failed:", e)

    # Commit AFTER loop finishes
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

    print(f"send_push: user={user_id}, subs found={len(subs)}")

    for sub in subs:
        try:
            private_key = os.environ.get("VAPID_PRIVATE_KEY")
            print(f"VAPID_PRIVATE_KEY present: {bool(private_key)}")
            print(f"Endpoint: {sub['endpoint'][:60]}")

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
                vapid_private_key=private_key,
                vapid_claims={
                    "sub": "mailto:wideminddevs@gmail.com"
                }
            )
            print("Push sent successfully!")
        except Exception as e:
            print(f"Push failed: {type(e).__name__}: {e}")


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

    # Delete all related records first
    c.execute("DELETE FROM payments WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM notifications WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM push_subscriptions WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM password_resets WHERE user_id=?", (user_id,))

    # Now delete the user
    c.execute("DELETE FROM users WHERE id=?", (user_id,))

    conn.commit()
    conn.close()
    flash("User deleted", "success")
    return redirect(url_for("admin_bp.users"))

# ---------------------
# USER FILTER PAGES
# ---------------------

def get_user_list(filter_type):
    conn = get_db()
    c = conn.cursor()

    base_query = """
        SELECT
            u.id, u.name, u.email, u.level, u.role, u.is_suspended,
            COALESCE(p.admin_override_status, p.status) AS payment_status
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
    else:  # all
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
        """, (user_id, 1026375))
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
        flash(f"A material with that filename already exists for this course.", "error")
        return redirect(f"/admin/courses/edit/{course_id}")

    # Upload to Supabase Storage
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    bucket = "materials"

    file_bytes = file.read()
    content_type = "application/pdf" if file_type == "pdf" else "audio/mpeg"

    upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{filename}"
    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": content_type,
        "x-upsert": "true"
    }

    import requests as req
    response = req.post(upload_url, headers=headers, data=file_bytes)

    if response.status_code not in (200, 201):
        flash(f"Upload to Supabase failed: {response.text}", "error")
        conn.close()
        return redirect(f"/admin/courses/edit/{course_id}")

    # Build public URL
    file_url = f"{supabase_url}/storage/v1/object/public/{bucket}/{filename}"

    # Save to Turso
    c.execute(
        "INSERT INTO materials (course_id, filename, file_type, title, file_url) VALUES (?, ?, ?, ?, ?)",
        (course_id, filename, file_type, title, file_url)
    )
    conn.commit()
    conn.close()
    # Send new material email to all paid users
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
        """)
        paid_users = c2.fetchall()
        conn2.close()
        for u in paid_users:
            send_new_material_email(
                to_email=u["email"],
                name=u["name"],
                material_title=title,
                course_title=course["course_title"] if course else "your course",
                file_type=file_type,
                course_id=course_id
            )
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

    # Delete from Supabase Storage
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    if supabase_url and supabase_key:
        import requests as req
        delete_url = f"{supabase_url}/storage/v1/object/materials/{material['filename']}"
        req.delete(delete_url, headers={
            "Authorization": f"Bearer {supabase_key}"
        })

    # Delete from Turso
    c.execute("DELETE FROM materials WHERE id=?", (material_id,))
    conn.commit()
    conn.close()
    return redirect(f"/admin/courses/edit/{material['course_id']}")