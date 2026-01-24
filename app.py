from flask import (
    Flask, render_template, redirect, session,
    request, jsonify, send_from_directory, abort, g
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

if os.environ.get("ENV") == "production":
    app.config["SESSION_COOKIE_SECURE"] = True
    app.debug = False

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=3600  # 1 hour
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
    if "user_id" in session:
        return redirect("/admin" if is_admin(session["user_id"]) else "/account")
    return render_template("login.html")

@app.route("/register-page")
def register_page():
    if "user_id" in session:
        return redirect("/admin" if is_admin(session["user_id"]) else "/account")
    return render_template("register.html")

@app.route("/account")
def account_page():
    if "user_id" not in session:
        return redirect("/login-page")
    if is_admin(session["user_id"]):
        return redirect("/admin")
    return render_template("account.html")

@app.before_request
def block_suspended_users():
    if "user_id" in session:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT is_suspended FROM users WHERE id=?", (session["user_id"],))
        user = c.fetchone()
        conn.close()
        if user and user["is_suspended"]:
            session.clear()
            return redirect("/login-page")
            
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
        (user_id, 100, "unpaid")
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
    if "user_id" not in session:
        abort(403)

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT status FROM payments WHERE user_id=?", (session["user_id"],))
    payment = c.fetchone()
    if not payment or payment["status"] != "paid":
        conn.close()
        abort(403)

    c.execute("""
        SELECT m.filename
        FROM materials m
        JOIN courses c ON m.course_id = c.id
        WHERE m.id=? AND m.file_type='audio'
    """, (material_id,))
    material = c.fetchone()
    conn.close()

    if not material:
        abort(404)

    return send_from_directory(app.config["UPLOAD_FOLDER"], material["filename"])

@app.route("/stream/pdf/<int:material_id>")
def stream_pdf(material_id):
    if "user_id" not in session:
        abort(403)

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT status FROM payments WHERE user_id=?", (session["user_id"],))
    payment = c.fetchone()
    if not payment or payment["status"] != "paid":
        conn.close()
        abort(403)

    c.execute("""
        SELECT m.filename
        FROM materials m
        JOIN courses c ON m.course_id = c.id
        WHERE m.id=? AND m.file_type='pdf'
    """, (material_id,))
    material = c.fetchone()
    conn.close()

    if not material:
        abort(404)

    return send_from_directory(app.config["UPLOAD_FOLDER"], material["filename"])

# =====================
# PAYMENT STATUS
# =====================
@app.route("/api/payment/status", methods=["GET"])
def payment_status():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    user_id = session["user_id"]

    # Admin users don't need payment
    if is_admin(user_id):
        return jsonify({
            "user_id": user_id,
            "amount": 0,
            "status": "admin",
            "reference": None,
            "paid_at": None
        })

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM payments WHERE user_id=?", (user_id,))
    payment = c.fetchone()

    if not payment:
        # No payment record, return default ₦100 unpaid
        default_payment = {
            "user_id": user_id,
            "amount": 100,
            "status": "unpaid",
            "reference": None,
            "paid_at": None
        }
        # Insert a default payment record
        c.execute(
            "INSERT INTO payments (user_id, amount, status) VALUES (?, ?, ?)",
            (user_id, 100, "unpaid")
        )
        conn.commit()
        conn.close()
        return jsonify(default_payment)

    # Prepare payment data
    payment_data = {key: payment[key] for key in payment.keys()}

    # If admin_override_status exists, it takes precedence
    if payment.get("admin_override_status"):
        payment_data["status"] = payment["admin_override_status"]

    # Verify with Paystack only if there's a reference
    elif payment_data.get("reference"):
        headers = {
            "Authorization": f"Bearer {os.environ.get('PAYSTACK_SECRET_KEY')}"
        }
        try:
            resp = requests.get(
                f"https://api.paystack.co/transaction/verify/{payment_data['reference']}",
                headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") and data["data"]["status"] == "success":
                # Update status to paid if not already marked
                if payment_data["status"] != "paid":
                    c.execute(
                        "UPDATE payments SET status='paid', admin_override_status=NULL, paid_at=datetime('now') WHERE user_id=?",
                        (user_id,)
                    )
                    conn.commit()
                    payment_data["status"] = "paid"
                    payment_data["paid_at"] = data["data"].get("paid_at")
            else:
                # Payment not successful, fallback to local status
                payment_data["status"] = payment_data.get("status", "unpaid")
        except requests.RequestException:
            # Network / API error, fallback to local status
            payment_data["status"] = payment_data.get("status", "unpaid")

    conn.close()
    return jsonify(payment_data)

# =====================
# PAYMENT SUCCESS
# =====================
@app.route("/payment-success")
def payment_success():
    return render_template("payment_success.html")

# =====================
# CONTACT FORM
# =====================
@app.route("/api/contact", methods=["POST"])
def submit_contact():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"redirect": "/login-page"}), 200

    if is_admin(user_id):
        return jsonify({"error": "Admins cannot send contact messages"}), 200

    data = request.get_json() or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    subject = data.get("subject", "").strip()
    message = data.get("message", "").strip()

    if not name or not email or not message:
        return jsonify({"error": "All required fields must be filled"}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO contact_messages (name, email, subject, message)
        VALUES (?, ?, ?, ?)
    """, (name, email, subject, message))
    conn.commit()
    conn.close()

    return jsonify({"message": "Message sent successfully"}), 201

# =====================
# LOGOUT
# =====================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login-page")

# =====================
# RUN
# =====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port, debug=True)