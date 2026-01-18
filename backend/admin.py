print(">>> admin.py imported")

from flask import Blueprint, render_template, jsonify, session, redirect, request, abort, has_request_context
from backend.db import get_db, is_admin, execute_with_fk_logging
from functools import wraps
from werkzeug.utils import secure_filename
import os
import uuid
import sqlite3
from datetime import datetime
import logging

# ---------------------
# BLUEPRINT
# ---------------------
admin_bp = Blueprint("admin_bp", __name__, url_prefix="/admin")

# ---------------------
# UPLOAD CONFIG
# ---------------------
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../files")
ALLOWED_EXTENSIONS = {"pdf", "mp3", "wav"}

# ---------------------
# LOGGER CONFIG (safe)
# ---------------------
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin_fk.log"))
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)

# ---------------------
# ADMIN GUARD
# ---------------------
def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session or not is_admin(session["user_id"]):
            return redirect("/auth/login")
        return func(*args, **kwargs)
    return wrapper

# ---------------------
# CSRF PROTECTION FOR ADMIN POST
# ---------------------
def csrf_protect():
    if not has_request_context():
        return
    if request.method == "POST":
        token = session.get("_csrf_token")
        header_token = request.headers.get("X-CSRF-Token")
        if not token or token != header_token:
            abort(403)

# ---------------------
# HELPER
# ---------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------------------
# DASHBOARD
# ---------------------
@admin_bp.route("/dashboard")
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
            u.id, u.name, u.email, u.level, u.role, u.is_suspended,
            u.created_at,
            p.status AS payment_status, p.created_at AS payment_created, p.paid_at
        FROM users u
        LEFT JOIN payments p ON u.id = p.user_id
        ORDER BY u.id DESC
    """)
    users = c.fetchall()
    conn.close()
    return render_template("admin/users.html", users=users)

@admin_bp.route("/users/suspend/<int:user_id>", methods=["POST"])
@admin_required
def toggle_suspend_user(user_id):
    csrf_protect()
    conn = get_db()
    c = conn.cursor()
    try:
        execute_with_fk_logging(c, """
            UPDATE users
            SET is_suspended = CASE WHEN is_suspended=1 THEN 0 ELSE 1 END
            WHERE id=?
        """, (user_id,))
        conn.commit()
    except sqlite3.IntegrityError as e:
        logger.warning(f"Suspend failed: {e}")
        conn.close()
        return jsonify({"error": "Action failed due to database integrity"}), 400
    conn.close()
    return jsonify({"message": "User suspension updated"}), 200

@admin_bp.route("/users/delete/<int:user_id>", methods=["POST"])
@admin_required
def delete_user(user_id):
    csrf_protect()
    conn = get_db()
    c = conn.cursor()
    try:
        execute_with_fk_logging(c, "DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
    except sqlite3.IntegrityError as e:
        logger.warning(f"Delete user failed: {e}")
        conn.close()
        return jsonify({"error": "Cannot delete user, related records exist"}), 400
    conn.close()
    return jsonify({"message": "User deleted"}), 200

@admin_bp.route("/users/mark-paid/<int:user_id>", methods=["POST"])
@admin_required
def toggle_payment(user_id):
    csrf_protect()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    if not user or user["role"] == "admin":
        conn.close()
        abort(400)

    c.execute("SELECT status FROM payments WHERE user_id=?", (user_id,))
    payment = c.fetchone()
    if not payment:
        conn.close()
        abort(404)

    new_status = "unpaid" if payment["status"] == "paid" else "paid"
    now = datetime.utcnow().isoformat()

    try:
        execute_with_fk_logging(c, """
            UPDATE payments
            SET status=?, paid_at=?
            WHERE user_id=?
        """, (new_status, now if new_status == "paid" else None, user_id))
        conn.commit()
    except sqlite3.IntegrityError as e:
        logger.warning(f"Toggle payment failed: {e}")
        conn.close()
        return jsonify({"error": "Cannot update payment due to database integrity"}), 400

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
    csrf_protect()
    conn = get_db()
    c = conn.cursor()
    try:
        execute_with_fk_logging(c, """
            INSERT INTO courses (course_code, course_title, description)
            VALUES (?, ?, ?)
        """, (
            request.form.get("course_code"),
            request.form.get("course_title"),
            request.form.get("description")
        ))
        conn.commit()
    except sqlite3.IntegrityError as e:
        logger.warning(f"Add course failed: {e}")
        conn.close()
        return jsonify({"error": "Cannot add course, check uniqueness and integrity"}), 400
    conn.close()
    return redirect("/admin/courses")

@admin_bp.route("/courses/edit/<int:course_id>", methods=["GET", "POST"])
@admin_required
def edit_course(course_id):
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        csrf_protect()
        try:
            execute_with_fk_logging(c, """
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
        except sqlite3.IntegrityError as e:
            logger.warning(f"Edit course failed: {e}")
            conn.close()
            return jsonify({"error": "Cannot edit course due to integrity error"}), 400

    c.execute("SELECT * FROM courses WHERE id=?", (course_id,))
    course = c.fetchone()
    c.execute("SELECT id, filename, file_type, title FROM materials WHERE course_id=?", (course_id,))
    materials = c.fetchall()
    conn.close()
    return render_template("admin/edit_course.html", course=course, materials=materials)

@admin_bp.route("/courses/delete/<int:course_id>", methods=["POST"])
@admin_required
def delete_course(course_id):
    csrf_protect()
    conn = get_db()
    c = conn.cursor()
    try:
        execute_with_fk_logging(c, "DELETE FROM courses WHERE id=?", (course_id,))
        conn.commit()
    except sqlite3.IntegrityError as e:
        logger.warning(f"Delete course failed: {e}")
        conn.close()
        return jsonify({"error": "Cannot delete course, related materials exist"}), 400
    conn.close()
    return jsonify({"message": "Course deleted"}), 200

# ---------------------
# MATERIALS
# ---------------------
@admin_bp.route("/courses/material/add/<file_type>/<int:course_id>", methods=["POST"])
@admin_required
def add_material(file_type, course_id):
    csrf_protect()
    file = request.files.get(file_type)
    title = request.form.get("title")
    if not file or not title or not allowed_file(file.filename):
        abort(400)

    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file.save(os.path.join(UPLOAD_FOLDER, filename))

    conn = get_db()
    c = conn.cursor()
    try:
        execute_with_fk_logging(c, """
            INSERT INTO materials (course_id, filename, file_type, title, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (course_id, filename, file_type, title, datetime.utcnow().isoformat()))
        conn.commit()
    except sqlite3.IntegrityError as e:
        logger.warning(f"Add material failed: {e}")
        conn.close()
        return jsonify({"error": "Cannot add material, check course exists"}), 400
    conn.close()
    return redirect(f"/admin/courses/edit/{course_id}")

@admin_bp.route("/courses/material/delete/<int:material_id>", methods=["POST"])
@admin_required
def delete_material(material_id):
    csrf_protect()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT filename, course_id FROM materials WHERE id=?", (material_id,))
    material = c.fetchone()
    if not material:
        conn.close()
        abort(404)

    filepath = os.path.join(UPLOAD_FOLDER, material["filename"])
    
    # -----------------------------
    # Properly handle missing file
    # -----------------------------
    if not os.path.exists(filepath):
        logger.warning(f"File {filepath} not found when deleting material id {material_id}")
    else:
        try:
            os.remove(filepath)
        except Exception as e:
            logger.warning(f"Failed to delete file {filepath}: {e}")

    try:
        execute_with_fk_logging(c, "DELETE FROM materials WHERE id=?", (material_id,))
        conn.commit()
    except sqlite3.IntegrityError as e:
        logger.warning(f"Delete material failed: {e}")
        conn.close()
        return jsonify({"error": "Cannot delete material due to integrity constraints"}), 400

    conn.close()
    return redirect(f"/admin/courses/edit/{material['course_id']}")