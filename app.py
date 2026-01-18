print(">>> app.py imported")

from flask import (
    Flask, render_template, redirect, session,
    request, jsonify, send_from_directory, abort, make_response
)
from flask_cors import CORS
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from backend.db import init_db, get_db, is_admin, execute_with_fk_logging
from backend.auth import auth_bp
from backend.admin import admin_bp
from backend.payment import payment_bp
from backend.webhook import webhook_bp
import secrets
import sqlite3
import logging

# -------------------------
# LOGGING
# -------------------------
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)

# -------------------------
# FLASK INIT
# -------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "supersecret")
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files")

if os.environ.get("ENV") == "production":
    app.debug = False
    app.config["SESSION_COOKIE_SECURE"] = True
else:
    app.debug = True

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1)
)

CORS(app, origins=os.environ.get(
    "FRONTEND_ORIGIN",
    "https://wide-mind-tutorial-gptu.onrender.com"
))

# -------------------------
# REGISTER BLUEPRINTS
# -------------------------
app.register_blueprint(admin_bp)
app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(payment_bp)
app.register_blueprint(webhook_bp)

# -------------------------
# INIT DB (Flask 3 SAFE)
# -------------------------
with app.app_context():
    init_db()

# -------------------------
# CSRF PROTECTION
# -------------------------
def generate_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(16)
    return session["_csrf_token"]

app.jinja_env.globals["csrf_token"] = generate_csrf_token

@app.before_request
def csrf_protect():
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
    if "user_id" in session:
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
# LOGIN FIX (COOKIE NAME)
# -------------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, password, role, is_suspended FROM users WHERE email=?", (email,))
    user = c.fetchone()
    conn.close()

    if not user or user["is_suspended"]:
        return jsonify({"error": "Invalid credentials"}), 403

    if not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid credentials"}), 403

    session.clear()
    session["user_id"] = user["id"]
    session["_csrf_token"] = secrets.token_hex(16)

    response = make_response(jsonify({"message": "Login successful"}))
    response.set_cookie(
        key="csrf_token",
        value=session["_csrf_token"],
        secure=True,
        httponly=True,
        samesite="Lax",
        path="/"
    )
    return response