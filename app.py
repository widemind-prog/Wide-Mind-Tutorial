print(">>> app.py imported")

from flask import (
    Flask, render_template, redirect, session,
    request, jsonify, send_from_directory, abort,
    make_response, has_request_context
)
from flask_cors import CORS
import os
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
from backend.db import init_db, get_db, is_admin
from backend.auth import auth_bp
from backend.admin import admin_bp
from backend.payment import payment_bp
from backend.webhook import webhook_bp
import secrets
import logging

# -------------------------
# LOGGING
# -------------------------
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(message)s"
)

# -------------------------
# FLASK INIT
# -------------------------
app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "supersecret")
app.config["UPLOAD_FOLDER"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "files"
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1)
)

if os.environ.get("ENV") == "production":
    app.debug = True
    secure_cookie = True
else:
    app.debug = True
    secure_cookie = False

CORS(
    app,
    origins=os.environ.get(
        "FRONTEND_ORIGIN",
        "https://wide-mind-tutorial-gptu.onrender.com"
    )
)

app.jinja_env.globals['now'] = datetime.utcnow

# -------------------------
# INIT DB
# -------------------------
with app.app_context():
    init_db()

# -------------------------
# REGISTER BLUEPRINTS
# -------------------------
app.register_blueprint(admin_bp)
app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(payment_bp)
app.register_blueprint(webhook_bp)

# -------------------------
# CSRF TOKEN
# -------------------------
def generate_csrf_token():
    if not has_request_context():
        return ""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(16)
    return session["_csrf_token"]

app.jinja_env.globals["csrf_token"] = generate_csrf_token

# -------------------------
# CSRF PROTECTION
# -------------------------
@app.before_request
def csrf_protect():
    if not has_request_context():
        return
    if request.path.startswith("/webhook/"):
        return
    if request.method == "POST":
        token = session.get("_csrf_token")
        form_token = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or token != form_token:
            abort(403)

# -------------------------
# BLOCK SUSPENDED USERS
# -------------------------
@app.before_request
def block_suspended_users():
    if not has_request_context() or "user_id" not in session:
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT is_suspended FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    conn.close()
    if user and user["is_suspended"]:
        session.clear()
        return redirect("/login-page")

# -------------------------
# SECURITY HEADERS
# -------------------------
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

# -------------------------
# LOGIN ROUTE
# -------------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, password, role, is_suspended FROM users WHERE email=?", (email,))
    user = c.fetchone()
    conn.close()

    if not user or user["is_suspended"] or not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid credentials"}), 403

    session.clear()
    session["user_id"] = user["id"]
    session["_csrf_token"] = secrets.token_hex(16)

    response = make_response(jsonify({"message": "Login successful"}))
    response.set_cookie(
        key="csrf_token",
        value=session["_csrf_token"],
        secure=secure_cookie,
        httponly=True,
        samesite="Lax",
        path="/"
    )
    return response

# -------------------------
# LOGOUT
# -------------------------
@app.route("/logout")
def logout():
    session.clear()
    response = make_response(redirect("/login"))
    response.set_cookie("session", "", expires=0, path="/", secure=secure_cookie, httponly=True, samesite="Lax")
    response.set_cookie("csrf_token", "", expires=0, path="/", secure=secure_cookie, httponly=True, samesite="Lax")
    return response

# -------------------------
# FRONTEND PAGES
# -------------------------

@app.route("/")
@app.route("/index")
def index():
    return render_template("index.html")
    if "user_id" in session:
        # Admin → admin dashboard
        if is_admin(session["user_id"]):
            return redirect("/dashboard")
        # Normal user → account page
        return redirect("/account")

@app.route("/login")
def login():
    return render_template("login.html")
    if "user_id" in session:
        # Admin → admin dashboard
        if is_admin(session["user_id"]):
            return redirect("/dashboard")
        # Normal user → account page
        return redirect("/account")
    
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")
    
@app.route("/register")
def register():
    return render_template("register.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

# -------------------------
# USER COURSES PAGE (course.html)
# -------------------------
@app.route("/course")
def course():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM courses ORDER BY id DESC")
    courses = c.fetchall()

    # Fetch materials with titles for each course
    courses_with_materials = []
    for course in courses:
        c.execute("SELECT id, filename, file_type, title FROM materials WHERE course_id=?", (course["id"],))
        materials = c.fetchall()
        courses_with_materials.append({"course": course, "materials": materials})

    conn.close()
    return render_template("course.html", courses=courses_with_materials)

# -------------------------
# STREAM FILES SECURELY
# -------------------------
ALLOWED_FILE_TYPES = {"pdf", "audio"}

def stream_file(material_id, file_type):
    if "user_id" not in session or file_type not in ALLOWED_FILE_TYPES:
        abort(403)

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT status FROM payments WHERE user_id=?", (session["user_id"],))
    payment = c.fetchone()
    if not payment or payment["status"] != "paid":
        conn.close()
        abort(403)

    c.execute("SELECT filename, file_type FROM materials WHERE id=?", (material_id,))
    material = c.fetchone()
    conn.close()
    if not material or material["file_type"] != file_type:
        abort(404)

    safe_filename = secure_filename(material["filename"])
    resp = send_from_directory(app.config["UPLOAD_FOLDER"], safe_filename)
    resp.headers["Cache-Control"] = "no-store"
    return resp

@app.route("/stream/audio/<int:material_id>")
def stream_audio(material_id):
    return stream_file(material_id, "audio")

@app.route("/stream/pdf/<int:material_id>")
def stream_pdf(material_id):
    return stream_file(material_id, "pdf")

# -------------------------
# PAYMENT SUCCESS PAGE
# -------------------------
@app.route("/payment-success")
def payment_success():
    return render_template("payment_success.html")

# -------------------------
# PAYMENT STATUS
# -------------------------
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

# -------------------------
# RUN APP
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port)