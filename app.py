from flask import (
    Flask, render_template, redirect, session,
    request, jsonify, send_from_directory, abort
)
from flask_cors import CORS
import os
from datetime import datetime
from werkzeug.security import generate_password_hash
from backend.db import init_db, get_db, is_admin
from backend.auth import auth_bp
from backend.admin import admin_bp
import requests
import hashlib
import hmac

app = Flask(__name__)
CORS(app)

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

# =====================
# REGISTER BLUEPRINTS
# =====================
app.register_blueprint(admin_bp)
app.register_blueprint(auth_bp, url_prefix="/api/auth")

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

    hashed_pw = generate_password_hash(data["password"])
    conn = get_db()
    c = conn.cursor()

    try:
        c.execute("""
            INSERT INTO users (name, email, password, department, level)
            VALUES (?, ?, ?, ?, ?)
        """, (
            data["name"],
            data["email"],
            hashed_pw,
            data["department"],
            data["level"]
        ))

        user_id = c.lastrowid

        c.execute("""
            INSERT INTO payments (user_id, amount, status)
            VALUES (?, 20000, 'unpaid')
        """)

        conn.commit()
    except Exception:
        conn.close()
        return jsonify({"error": "Email already exists"}), 400

    conn.close()
    return jsonify({"redirect": "/login-page"}), 201

# =====================
# COURSES FOR USERS (ALL VISIBLE, UNPAID OR PAID)
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
# SINGLE COURSE PAGE (PAYMENT REQUIRED TO ACCESS)
# =====================
@app.route("/course/<int:course_id>")
def course_page(course_id):
    if "user_id" not in session:
        return redirect("/login-page")

    conn = get_db()
    c = conn.cursor()

    # Check if paid
    c.execute("SELECT status FROM payments WHERE user_id=?", (session["user_id"],))
    payment = c.fetchone()
    if not payment or payment["status"] != "paid":
        conn.close()
        return "<h3>Payment required to access courses</h3>", 403

    # Fetch course
    c.execute("SELECT * FROM courses WHERE id=?", (course_id,))
    course = c.fetchone()
    if not course:
        conn.close()
        abort(404)

    # Fetch all materials with custom names (titles)
    c.execute("SELECT * FROM materials WHERE course_id=? AND file_type='audio'", (course_id,))
    audios = c.fetchall()

    c.execute("SELECT * FROM materials WHERE course_id=? AND file_type='pdf'", (course_id,))
    pdfs = c.fetchall()

    conn.close()

    return render_template(
        "course.html",
        course=course,
        audios=audios,
        pdfs=pdfs
    )

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

    c.execute(
        "SELECT id FROM materials WHERE course_id=? AND file_type='pdf'",
        (course_id,)
    )
    pdf = c.fetchone()
    conn.close()

    if not pdf:
        abort(404)

    return render_template(
        "pdf_viewer.html",
        course=course,
        pdf_id=pdf["id"]
    )

# =====================
# STREAM FILES
# =====================
@app.route("/stream/audio/<int:material_id>")
def stream_audio(material_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT filename FROM materials WHERE id=? AND file_type='audio'",
        (material_id,)
    )
    material = c.fetchone()
    conn.close()

    if not material:
        abort(404)

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        material["filename"]
    )

@app.route("/stream/pdf/<int:material_id>")
def stream_pdf(material_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT filename FROM materials WHERE id=? AND file_type='pdf'",
        (material_id,)
    )
    material = c.fetchone()
    conn.close()

    if not material:
        abort(404)

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        material["filename"]
    )

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

# =====================
# PAYMENT INIT
# =====================
@app.route("/api/payment/init", methods=["POST"])
def init_payment():
    if "user_id" not in session or is_admin(session["user_id"]):
        abort(403)

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    conn.close()

    headers = {
        "Authorization": f"Bearer {app.config['PAYSTACK_SECRET_KEY']}",
        "Content-Type": "application/json"
    }

    payload = {
        "email": user["email"],
        "amount": 20000 * 100,
        "callback_url": "https://wide-mind-tutorial-gptu.onrender.com/payment-success"
    }

    res = requests.post(
        "https://api.paystack.co/transaction/initialize",
        json=payload,
        headers=headers
    )

    return jsonify(res.json())

# =====================
# PAYMENT CALLBACK
# =====================
@app.route("/payment-success")
def payment_success():
    reference = request.args.get("reference")
    if not reference:
        abort(400)

    headers = {
        "Authorization": f"Bearer {app.config['PAYSTACK_SECRET_KEY']}"
    }

    res = requests.get(
        f"https://api.paystack.co/transaction/verify/{reference}",
        headers=headers
    )

    data = res.json()

    if data["status"] and data["data"]["status"] == "success":
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            UPDATE payments
            SET status='paid', paid_at=datetime('now')
            WHERE user_id=?
        """, (session["user_id"],))
        conn.commit()
        conn.close()
        return redirect("/account")

    return "<h3>Payment failed</h3>", 400

# =====================
# PAYSTACK WEBHOOK
# =====================
@app.route("/paystack/webhook", methods=["POST"])
def paystack_webhook():
    signature = request.headers.get("x-paystack-signature")
    payload = request.get_data()

    expected = hmac.new(
        app.config["PAYSTACK_SECRET_KEY"].encode(),
        payload,
        hashlib.sha512
    ).hexdigest()

    if signature != expected:
        abort(403)

    event = request.get_json()
    if event["event"] == "charge.success":
        email = event["data"]["customer"]["email"]
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            UPDATE payments
            SET status='paid', paid_at=datetime('now')
            WHERE user_id=(SELECT id FROM users WHERE email=?)
        """, (email,))
        conn.commit()
        conn.close()

    return "", 200

# =====================
# LOGOUT
# =====================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login-page")

# =====================
# ERRORS
# =====================
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

# =====================
# RUN
# =====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port, debug=True)