from flask import Flask, render_template, redirect, session, request, jsonify, send_from_directory, abort
from flask_cors import CORS
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from backend.db import init_db, get_db
from backend.auth import auth_bp
import requests, secrets
from flask_mail import Mail, Message

app = Flask(__name__)
CORS(app)

# ------------------------
# CONFIG
# ------------------------
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "supersecret")
app.config["PAYSTACK_SECRET_KEY"] = os.environ.get("PAYSTACK_SECRET_KEY")
app.config["PAYSTACK_PUBLIC_KEY"] = os.environ.get("PAYSTACK_PUBLIC_KEY")
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files")

# Flask-Mail config (Gmail example)
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.environ.get("EMAIL_USER"),
    MAIL_PASSWORD=os.environ.get("EMAIL_PASS"),
    MAIL_DEFAULT_SENDER=os.environ.get("EMAIL_USER")
)
mail = Mail(app)

# ------------------------
# INIT
# ------------------------
init_db()
app.register_blueprint(auth_bp, url_prefix="/api/auth")

@app.context_processor
def inject_now():
    return {"now": datetime.utcnow}

# =====================
# PAGES
# =====================
@app.route("/")
def home():
    return redirect("/account") if "user_id" in session else render_template("index.html")

@app.route("/home")
def home_redirect(): return redirect("/")
@app.route("/about") 
def about_page(): return render_template("about.html")
@app.route("/contact") 
def contact_page(): return render_template("contact.html")
@app.route("/privacy") 
def privacy_page(): return render_template("privacy.html")
@app.route("/register-page") 
def register_page(): return render_template("register.html")
@app.route("/login-page") 
def login_page(): return render_template("login.html")
@app.route("/account")
def account_page():
    if "user_id" not in session:
        return redirect("/login-page")
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
    token = secrets.token_urlsafe(16)  # email verification token

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (name, email, password, department, level, is_verified, verification_token) VALUES (?, ?, ?, ?, ?, 0, ?)",
            (name, email, hashed_pw, department, level, token)
        )
        conn.commit()
        user_id = c.lastrowid
        c.execute(
            "INSERT INTO payments (user_id, amount, status) VALUES (?, ?, ?)",
            (user_id, 20000, "unpaid")
        )
        conn.commit()
    except:
        conn.close()
        return jsonify({"error": "Email already exists"}), 400

    # Send verification email
    verify_link = f"{request.host_url}verify-email?token={token}"
    msg = Message(
        "Verify Your Email",
        recipients=[email],
        html=f"<p>Hello {name},</p><p>Click to verify your email:</p><a href='{verify_link}'>Verify Email</a>"
    )
    mail.send(msg)
    conn.close()
    return jsonify({"message": "Registration successful! Check your email to verify your account.", "redirect": "/login-page"}), 201

# =====================
# EMAIL VERIFICATION
# =====================
@app.route("/verify-email")
def verify_email():
    token = request.args.get("token")
    if not token:
        return "<h3>Invalid verification link</h3>", 400

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, is_verified FROM users WHERE verification_token=?", (token,))
    user = c.fetchone()
    if not user:
        conn.close()
        return "<h3>Invalid or expired link</h3>", 400
    if user["is_verified"]:
        conn.close()
        return "<h3>Email already verified!</h3>"

    c.execute("UPDATE users SET is_verified=1, verification_token=NULL WHERE id=?", (user["id"],))
    conn.commit()
    conn.close()
    return "<h3>Email verified successfully ✅. You can now log in.</h3>"

# =====================
# LOGIN
# =====================
@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email=?", (email,))
    user = c.fetchone()
    conn.close()

    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid credentials"}), 401
    if not user["is_verified"]:
        return jsonify({"error": "Email not verified. Check your inbox."}), 403

    session["user_id"] = user["id"]

    # Send welcome email only once
    if not user.get("first_login"):
        conn = get_db()
        c = conn.cursor()
        msg = Message(
            "Welcome to Wide Mind Tutorials 🚀",
            recipients=[user["email"]],
            html=f"<p>Hello {user['name']},</p><p>Welcome! Enjoy your learning journey.</p>"
        )
        mail.send(msg)
        c.execute("UPDATE users SET first_login=datetime('now') WHERE id=?", (user["id"],))
        conn.commit()
        conn.close()

    return jsonify({"message": "Login successful", "redirect": "/account"}), 200

# =====================
# PAYMENT CONFIRMATION
# =====================
@app.route("/api/payment/mark_paid", methods=["POST"])
def mark_paid():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE payments SET status='paid', paid_at=datetime('now') WHERE user_id=?", (session["user_id"],))
    conn.commit()

    # Send payment confirmation email
    c.execute("SELECT name, email FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    msg = Message(
        "Payment Successful ✅",
        recipients=[user["email"]],
        html=f"<p>Hello {user['name']},</p><p>Your payment of ₦20000 was successful. You now have full access to courses.</p>"
    )
    mail.send(msg)
    conn.close()
    return jsonify({"message": "Payment marked as paid"}), 200

# =====================
# OTHER ROUTES (COURSES, PDF, STREAM) 
# =====================
# ... Keep your existing routes here (unchanged) ...
# =====================
# RUN
# =====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port, debug=True)