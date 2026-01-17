from flask import Blueprint, render_template, jsonify, session, redirect, request, abort
from backend.db import get_db, is_admin
from functools import wraps
import os
from werkzeug.utils import secure_filename

admin_bp = Blueprint("admin_bp", __name__, url_prefix="/admin")

UPLOAD_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "../files"
)

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
    return render_template("admin/dashboard.html")

# ---------------------
# USERS
# ---------------------

@admin_bp.route("/users")
@admin_required
def users():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT
            u.id,
            u.name,
            u.email,
            u.level,
            u.role,
            u.is_suspended,
            p.status AS payment_status
        FROM users u
        LEFT JOIN payments p ON u.id = p.user_id
        ORDER BY u.id DESC
    """)
    users = c.fetchall()
    conn.close()
    return render_template("admin/users.html", users=users)

# Toggle suspend/unsuspend with same button
@admin_bp.route("/users/suspend/<int:user_id>", methods=["POST"])
@admin_required
def toggle_suspend_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET is_suspended = CASE WHEN is_suspended=1 THEN 0 ELSE 1 END
        WHERE id=?
    """, (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "User suspension updated"}), 200

# Delete user
@admin_bp.route("/users/delete/<int:user_id>", methods=["POST"])
@admin_required
def delete_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "User deleted"}), 200

# Toggle mark paid / unpaid
@admin_bp.route("/users/mark-paid/<int:user_id>", methods=["POST"])
@admin_required
def toggle_payment(user_id):
    conn = get_db()
    c = conn.cursor()

    # Do not allow admin accounts
    c.execute("SELECT role FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    if not user or user["role"] == "admin":
        conn.close()
        abort(400)

    # Check current status
    c.execute("SELECT status FROM payments WHERE user_id=?", (user_id,))
    payment = c.fetchone()
    if not payment:
        conn.close()
        abort(404)

    new_status = "unpaid" if payment["status"] == "paid" else "paid"
    c.execute("""
        UPDATE payments
        SET status=?, paid_at=datetime('now')
        WHERE user_id=?
    """, (new_status, user_id))
    conn.commit()
    conn.close()
    return jsonify({"message": f"Payment status set to {new_status}"}), 200

# ---------------------
# COURSES
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
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO courses (course_code, course_title, description)
        VALUES (?, ?, ?)
    """, (
        request.form.get("course_code"),
        request.form.get("course_title"),
        request.form.get("description")
    ))
    conn.commit()
    conn.close()
    return redirect("/admin/courses")

@admin_bp.route("/courses/edit/<int:course_id>", methods=["GET", "POST"])
@admin_required
def edit_course(course_id):
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        c.execute("""
            UPDATE courses
            SET course_code=?, course_title=?, description=?
            WHERE id=?
        """, (
            request.form.get("course_code"),
            request.form.get("course_title"),
            request.form.get("description"),
            course_id
        ))
        conn.commit()

    # Fetch course details
    c.execute("SELECT * FROM courses WHERE id=?", (course_id,))
    course = c.fetchone()

    # Fetch materials
    c.execute("""
        SELECT id, filename, file_type
        FROM materials
        WHERE course_id=?
    """, (course_id,))
    materials = c.fetchall()

    conn.close()
    return render_template(
        "admin/edit_course.html",
        course=course,
        materials=materials
    )

@admin_bp.route("/courses/delete/<int:course_id>", methods=["POST"])
@admin_required
def delete_course(course_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM courses WHERE id=?", (course_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Course deleted"}), 200

# ---------------------
# MATERIALS
# ---------------------
@admin_bp.route("/courses/material/add/<file_type>/<int:course_id>", methods=["POST"])
@admin_required
def add_material(file_type, course_id):
    file = request.files.get(file_type)
    title = request.form.get("title")  # <-- fetch custom title
    if not file or not title:
        abort(400)

    filename = secure_filename(file.filename)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file.save(os.path.join(UPLOAD_FOLDER, filename))

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO materials (course_id, filename, file_type, title)
        VALUES (?, ?, ?, ?)
    """, (course_id, filename, file_type, title))
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

    filepath = os.path.join(UPLOAD_FOLDER, material["filename"])
    if os.path.exists(filepath):
        os.remove(filepath)

    c.execute("DELETE FROM materials WHERE id=?", (material_id,))
    conn.commit()
    conn.close()
    return redirect(f"/admin/courses/edit/{material['course_id']}")