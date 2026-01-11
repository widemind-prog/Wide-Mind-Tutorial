from flask import Flask, render_template, redirect, session, request, jsonify, send_from_directory, abort
from flask_cors import CORS
import os
from datetime import datetime
from werkzeug.security import check_password_hash, generate_password_hash
from backend.db import init_db, get_db
from backend.auth import auth_bp

app = Flask(__name__)
CORS(app)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files")

# Initialize database
init_db()

# Register auth blueprint (UNCHANGED)
app.register_blueprint(auth_bp, url_prefix="/api/auth")

# Inject current time into templates (UNCHANGED)
@app.context_processor
def inject_now():
    return {"now": datetime.utcnow}

# =====================
# ORIGINAL ROUTES (UNCHANGED)
# =====================

@app.route("/")
def home():
    if "user_id" in session:
        return redirect("/account")
    return render_template("index.html")

@app.route("/home")
def home_redirect():
    if "user_id" in session:
        return redirect("/account")
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

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name, department, level, password FROM users WHERE email=?", (email,))
    user = c.fetchone()
    conn.close()

    if user and check_password_hash(user["password"], password):
        session.clear()
        session["user_id"] = user["id"]
        return jsonify({"message": "Login successful", "redirect": "/account"}), 200

    return jsonify({"error": "Invalid credentials"}), 401

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

@app.route("/account")
def account_page():
    if "user_id" not in session:
        return redirect("/login-page")
    return render_template("account.html")

@app.route("/api/courses/my")
def my_courses():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, course_code, course_title FROM courses")
    courses = [
        {"id": row["id"], "code": row["course_code"], "title": row["course_title"]}
        for row in c.fetchall()
    ]
    conn.close()
    return jsonify({"courses": courses})

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
        return "Payment required", 403

    c.execute("SELECT id, course_code, course_title, description FROM courses WHERE id=?", (course_id,))
    course = c.fetchone()

    c.execute("SELECT id, filename, file_type FROM materials WHERE course_id=?", (course_id,))
    materials = c.fetchall()
    conn.close()

    if not course:
        return redirect("/")

    audio_id = None
    pdf_id = None

    for m in materials:
        if m["file_type"] == "audio":
            audio_id = m["id"]
        elif m["file_type"] == "pdf":
            pdf_id = m["id"]

    return render_template(
        "course.html",
        course=course,
        audio_id=audio_id,
        pdf_id=pdf_id
    )

# =====================
# 🔐 NEW PROTECTED FILE ROUTES (ADDED ONLY)
# =====================

@app.route("/stream/audio/<int:material_id>")
def stream_audio(material_id):
    if "user_id" not in session:
        abort(401)

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT status FROM payments WHERE user_id=?", (session["user_id"],))
    payment = c.fetchone()
    if not payment or payment["status"] != "paid":
        conn.close()
        abort(403)

    c.execute("SELECT filename FROM materials WHERE id=? AND file_type='audio'", (material_id,))
    file = c.fetchone()
    conn.close()

    if not file:
        abort(404)

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        file["filename"],
        as_attachment=False
    )

@app.route("/stream/pdf/<int:material_id>")
def stream_pdf(material_id):
    if "user_id" not in session:
        abort(401)

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT status FROM payments WHERE user_id=?", (session["user_id"],))
    payment = c.fetchone()
    if not payment or payment["status"] != "paid":
        conn.close()
        abort(403)

    c.execute("SELECT filename FROM materials WHERE id=? AND file_type='pdf'", (material_id,))
    file = c.fetchone()
    conn.close()

    if not file:
        abort(404)

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        file["filename"],
        as_attachment=False
    )

@app.route("/course/<int:course_id>/pdf")
def pdf_viewer(course_id):
    if "user_id" not in session:
        return redirect("/login-page")

    conn = get_db()
    c = conn.cursor()

    # Check payment
    c.execute("SELECT status FROM payments WHERE user_id=?", (session["user_id"],))
    payment = c.fetchone()
    if not payment or payment["status"] != "paid":
        conn.close()
        abort(403)

    # Get PDF material ID
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
        pdf_id=pdf["id"]
    )
    
# =====================
# PAYMENT ROUTES (UNCHANGED)
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
        return jsonify({"error": "Payment record not found"}), 404

    return jsonify({"amount": payment["amount"], "status": payment["status"]})

@app.route("/api/payment/mark_paid", methods=["POST"])
def mark_paid():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE payments SET status=? WHERE user_id=?", ("paid", session["user_id"]))
    conn.commit()
    conn.close()

    return jsonify({"message": "Payment marked as paid"}), 200

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login-page")

# =====================
# ERROR HANDLER (UNCHANGED)
# =====================

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

# =====================
# RUN SERVER (UNCHANGED)
# =====================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port, debug=True)