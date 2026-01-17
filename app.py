from flask import (
    Flask, render_template, redirect, session,
    request, jsonify, send_from_directory, abort
)
from flask_cors import CORS
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from backend.db import init_db, get_db, is_admin
from backend.auth import auth_bp
from backend.admin import admin_bp
from backend.payment import payment_bp
from backend.webhook import webhook_bp

import requests
import hashlib
import hmac

app = Flask(__name__)

# =====================
# CONFIG
# =====================
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "supersecret")
app.config["PAYSTACK_SECRET_KEY"] = os.environ.get("PAYSTACK_SECRET_KEY")
app.config["PAYSTACK_PUBLIC_KEY"] = os.environ.get("PAYSTACK_PUBLIC_KEY")
app.config["UPLOAD_FOLDER"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "files"
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

# =====================
# REGISTER BLUEPRINTS
# =====================
app.register_blueprint(admin_bp)
app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(payment_bp)
app.register_blueprint(webhook_bp)

# =====================
# INITIALIZE DB
# =====================
init_db()

# =====================
# TEMPLATE CONTEXT
# =====================
@app.context_processor
def inject_now():
    return {"now": datetime.utcnow}

# =====================
# PAGES
# =====================
@app.route("/")
def home():
    if "user_id" in session:
        return redirect("/admin" if is_admin(session["user_id"]) else "/account")
    return render_template("index.html")

@app.route("/home")
def home_redirect():
    return redirect("/")

@app.route("/about")
def about_page():
    return render_template("about.html")

@app.route("/contact")
def contact_page():
    return render_template("contact.html")

@app.route("/privacy")
def privacy_page():
    return render_template("privacy.html")

@app.route("/login-page")
def login_page():
    return render_template("login.html")

@app.route("/register-page")
def register_page():
    return render_template("register.html")

@app.route("/account")
def account_page():
    if "user_id" not in session:
        return redirect("/login-page")
    if is_admin(session["user_id"]):
        return redirect("/admin")
    return render_template("account.html")

# =====================
# REGISTER
# =====================
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    department = data.get("department")
    level = data.get("level")

    if not all([name, email, password, department, level]):
        return jsonify({"error": "All fields are required"}), 400

    hashed_pw = generate_password_hash(password)
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id FROM users WHERE email=?", (email,))
    if c.fetchone():
        conn.close()
        return jsonify({"error": "Email already exists"}), 400

    c.execute(
        "INSERT INTO users (name, email, password, department, level) VALUES (?, ?, ?, ?, ?)",
        (name, email, hashed_pw, department, level)
    )
    user_id = c.lastrowid

    c.execute(
        "INSERT INTO payments (user_id, amount, status) VALUES (?, ?, ?)",
        (user_id, 20000, "unpaid")
    )

    conn.commit()
    conn.close()

    return jsonify({"message": "Registration successful", "redirect": "/login-page"}), 201

# =====================
# COURSES FOR USERS
# =====================
@app.route("/api/courses/my")
def my_courses():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, course_code, course_title FROM courses ORDER BY id DESC")
    courses = [
        {"id": r["id"], "code": r["course_code"], "title": r["course_title"]}
        for r in c.fetchall()
    ]
    conn.close()

    return jsonify({"courses": courses})

# =====================
# COURSE PAGE
# =====================
@app.route("/course/<int:course_id>")
def course_page(course_id):
    if "user_id" not in session:
        return redirect("/login-page")

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT status FROM payments WHERE user_id=?", (session["user_id"],))
    payment = c.fetchone()
    if not payment or payment["status"] != "paid":
        conn.close()
        return "<h3>Payment required to access courses</h3>", 403

    c.execute("SELECT * FROM courses WHERE id=?", (course_id,))
    course = c.fetchone()
    if not course:
        conn.close()
        abort(404)

    c.execute("SELECT * FROM materials WHERE course_id=? AND file_type='audio'", (course_id,))
    audios = c.fetchall()

    c.execute("SELECT * FROM materials WHERE course_id=? AND file_type='pdf'", (course_id,))
    pdfs = c.fetchall()

    conn.close()

    return render_template("course.html", course=course, audios=audios, pdfs=pdfs)

# =====================
# PDF VIEWER
# =====================
@app.route("/course/<int:course_id>/pdf")
def pdf_viewer(course_id):
    if "user_id" not in session:
        return redirect("/login-page")

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT status FROM payments WHERE user_id=?", (session["user_id"],))
    payment = c.fetchone()
    if not payment or payment["status"] != "paid":
        conn.close()
        return "<h3>Payment required to access PDF</h3>", 403

    c.execute("SELECT * FROM courses WHERE id=?", (course_id,))
    course = c.fetchone()
    if not course:
        conn.close()
        abort(404)

    c.execute("SELECT id FROM materials WHERE course_id=? AND file_type='pdf'", (course_id,))
    pdf = c.fetchone()
    conn.close()

    if not pdf:
        abort(404)

    return render_template("pdf_viewer.html", course=course, pdf_id=pdf["id"])

# =====================
# STREAM FILES
# =====================
@app.route("/stream/audio/<int:material_id>")
def stream_audio(material_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT filename FROM materials WHERE id=? AND file_type='audio'", (material_id,))
    material = c.fetchone()
    conn.close()

    if not material:
        abort(404)

    return send_from_directory(app.config["UPLOAD_FOLDER"], material["filename"])

@app.route("/stream/pdf/<int:material_id>")
def stream_pdf(material_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT filename FROM materials WHERE id=? AND file_type='pdf'", (material_id,))
    material = c.fetchone()
    conn.close()

    if not material:
        abort(404)

    return send_from_directory(app.config["UPLOAD_FOLDER"], material["filename"])

# =====================
# PAYMENT STATUS
# =====================
@app.route("/api/payment/status")
def payment_status():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    if is_admin(session["user_id"]):
        return jsonify({"status": "admin"})

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT amount, status FROM payments WHERE user_id=?", (session["user_id"],))
    payment = c.fetchone()
    conn.close()

    if not payment:
        return jsonify({"amount": 20000, "status": "unpaid"})

    return jsonify({"amount": payment["amount"], "status": payment["status"]})
    
@app.route("/payment-success")
def payment_success():
    return render_template("payment_success.html")

# =====================
# LOGOUT
# =====================
@app.route("/logout")
def logout():
    session.clear()  # clears all session data
    return redirect("/login-page")  # redirect to login page
    
# =====================
# RUN
# =====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port, debug=True)