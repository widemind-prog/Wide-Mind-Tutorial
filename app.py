from flask import Flask, render_template, redirect, session, request, jsonify, send_from_directory, abort
from flask_cors import CORS
import os
from datetime import datetime
from werkzeug.security import generate_password_hash
from backend.db import init_db, get_db
from backend.auth import auth_bp
import requests

app = Flask(__name__)
CORS(app)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
app.config["PAYSTACK_SECRET_KEY"] = os.environ.get("PAYSTACK_SECRET_KEY")
app.config["PAYSTACK_PUBLIC_KEY"] = os.environ.get("PAYSTACK_PUBLIC_KEY")
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files")

# Initialize database
init_db()

# Register auth blueprint
app.register_blueprint(auth_bp, url_prefix="/api/auth")

# Inject current time into templates
@app.context_processor
def inject_now():
    return {"now": datetime.utcnow}

# =====================
# PAGES
# =====================
@app.route("/")
def home():
    if "user_id" in session:
        return redirect("/account")
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

@app.route("/register-page")
def register_page():
    return render_template("register.html")

@app.route("/login-page")
def login_page():
    return render_template("login.html")

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
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (name, email, password, department, level) VALUES (?, ?, ?, ?, ?)",
            (name, email, hashed_pw, department, level)
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

    conn.close()
    return jsonify({"message": "Registration successful", "redirect": "/login-page"}), 201

# =====================
# COURSES
# =====================
@app.route("/api/courses/my")
def my_courses():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, course_code, course_title FROM courses")
    courses = [{"id": r["id"], "code": r["course_code"], "title": r["course_title"]} for r in c.fetchall()]
    conn.close()
    return jsonify({"courses": courses})

# =====================
# PAYMENT STATUS
# =====================
@app.route("/api/payment/status")
def payment_status():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT amount, status FROM payments WHERE user_id=?", (session["user_id"],))
    payment = c.fetchone()
    conn.close()
    if not payment:
        return jsonify({"amount": 20000, "status": "unpaid"})
    return jsonify({"amount": payment["amount"], "status": payment["status"]})

# =====================
# STREAM FILES & COURSES
# =====================
# (Keep your existing /course/<id>, /stream/audio/<id>, /stream/pdf/<id>, etc.)
# ... same as before

# =====================
# PAYMENT INIT & MARK PAID
# =====================
@app.route("/api/payment/init", methods=["POST"])
def init_payment():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    conn.close()

    headers = {"Authorization": f"Bearer {app.config['PAYSTACK_SECRET_KEY']}", "Content-Type": "application/json"}
    payload = {"email": user["email"], "amount": 20000 * 100, "callback_url": "https://your-domain.com/payment-success"}

    res = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    return jsonify(res.json())

@app.route("/api/payment/mark_paid", methods=["POST"])
def mark_paid():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE payments SET status='paid', paid_at=datetime('now') WHERE user_id=?", (session["user_id"],))
    conn.commit()
    conn.close()
    return jsonify({"message": "Payment marked as paid"}), 200

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