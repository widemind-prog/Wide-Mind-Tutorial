from gevent import monkey
monkey.patch_all()
from flask import (
    Flask, render_template, redirect, session,
    request, jsonify, send_from_directory, abort
)
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
from extensions import socketio
from backend.db import init_db, get_db, is_admin, get_trial_course_for
from backend.auth import auth_bp
from backend.email_service import send_welcome_email, send_otp_email
from backend.admin import admin_bp
from backend.payment import payment_bp, get_amount_for_level, get_rerun_amount
from backend.webhook import webhook_bp
from backend.otp import otp_bp
from backend.progress import progress_bp, get_trial_status
import hashlib, random
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "supersecret")
app.config["PAYSTACK_SECRET_KEY"] = os.environ.get("PAYSTACK_SECRET_KEY")
app.config["PAYSTACK_PUBLIC_KEY"] = os.environ.get("PAYSTACK_PUBLIC_KEY")
app.config["VAPID_PUBLIC_KEY"] = os.environ.get("VAPID_PUBLIC_KEY")
UPLOAD_BASE = os.environ.get("UPLOAD_PATH", "/tmp/uploads")
os.makedirs(UPLOAD_BASE, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_BASE
if os.environ.get("ENV") == "production":
    app.config["SESSION_COOKIE_SECURE"] = True
    app.debug = False
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=3)
)
socketio.init_app(app)
app.register_blueprint(admin_bp)
app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(payment_bp)
app.register_blueprint(webhook_bp)
app.register_blueprint(otp_bp)
app.register_blueprint(progress_bp)
init_db()
@app.context_processor
def inject_config():
    return {"config": {"VAPID_PUBLIC_KEY": app.config["VAPID_PUBLIC_KEY"]}}
@app.context_processor
def inject_now():
    return {"now": datetime.utcnow}
# =====================
# ACCESS DECISION HELPER
# =====================
def get_access_state(user_id):
    """
    Returns dict describing the user's current access state.
    Order:
      1. Paid -> full access
      2. Active trial -> trial access (the course flagged is_trial for the
         user's own level + semester — resolved dynamically, not a fixed id)
      3. Verified + trial expired -> payment wall
      4. Not verified -> needs email verification
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT u.is_verified, u.trial_started_at, u.level, u.semester,
               COALESCE(p.admin_override_status, p.status) AS payment_status,
               p.amount
        FROM users u
        LEFT JOIN payments p ON u.id=p.user_id
        WHERE u.id=?
        ORDER BY p.id DESC LIMIT 1
    """, (user_id,))
    user = c.fetchone()
    conn.close()
    if not user:
        return {"state": "unknown"}
    is_paid = user["payment_status"] == "paid"
    if is_paid:
        return {"state": "paid"}
    if not user["is_verified"]:
        return {"state": "unverified"}
    trial = get_trial_status(user)
    if trial["active"]:
        trial_course = get_trial_course_for(user["level"], user["semester"])
        return {
            "state": "trial",
            "trial": trial,
            "trial_course_id": trial_course["id"] if trial_course else None,
            "trial_course": trial_course,
        }
    return {"state": "trial_expired"}
# =====================
# BEFORE REQUEST
# =====================
@app.before_request
def force_custom_domain():
    host = request.host
    if "onrender.com" in host:
        return redirect("https://www.widemindtutorial.com" + request.full_path, 301)
@app.before_request
def make_session_permanent():
    session.permanent = True
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
# PAGES
# =====================
@app.route("/")
def home():
    if "user_id" in session:
        return redirect("/admin" if is_admin(session["user_id"]) else "/account")
    return render_template("index.html")
@app.route("/home")
def home_redirect(): return redirect("/")
@app.route("/about")
def about_page(): return render_template("about.html")
@app.route("/contact")
def contact_page(): return render_template("contact.html")
@app.route("/privacy")
def privacy_page(): return render_template("privacy.html")
@app.route("/login-page")
def login_page():
    if "user_id" in session:
        return redirect("/admin" if is_admin(session["user_id"]) else "/account")
    return render_template("login.html")
@app.route("/forgot-password-page")
def forgot_password_page(): return render_template("forgot_password.html")
@app.route("/reset-password")
def reset_password_page(): return render_template("reset_password.html")
@app.route("/register-page")
def register_page():
    if "user_id" in session:
        return redirect("/admin" if is_admin(session["user_id"]) else "/account")
    return render_template("register.html")
@app.route("/verify-email")
def verify_email_page():
    if "user_id" not in session:
        return redirect("/login-page")
    # Already verified — go to account
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT is_verified FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    conn.close()
    if user and user["is_verified"]:
        return redirect("/account")
    return render_template("verify_email.html")
@app.route("/account")
def account_page():
    if "user_id" not in session:
        return redirect("/login-page")
    if is_admin(session["user_id"]):
        return redirect("/admin")
    # Unverified — redirect to verify
    access = get_access_state(session["user_id"])
    if access["state"] == "unverified":
        return redirect("/verify-email")
    return render_template("account.html")
@app.route("/service-worker.js")
def service_worker():
    return send_from_directory("static/js", "service-worker.js", mimetype="application/javascript")
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
    semester = data.get("semester")
    if not all([name, email, password, department, level, semester]):
        return jsonify({"error": "All fields are required"}), 400
    if str(level) not in ("300", "400", "500"):
        return jsonify({"error": "Invalid level"}), 400
    try:
        semester = int(semester)
        if semester not in (1, 2): raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid semester value"}), 400
    hashed_pw = generate_password_hash(password)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=?", (email,))
    if c.fetchone():
        conn.close()
        return jsonify({"error": "Email already exists"}), 400
    c.execute("""
        INSERT INTO users (name, email, password, department, level, semester, is_verified)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """, (name, email, hashed_pw, department, level, semester))
    user_id = c.lastrowid
    amount = get_amount_for_level(level)
    c.execute("INSERT INTO payments (user_id, amount, status) VALUES (?, ?, 'unpaid')",
              (user_id, amount))
    conn.commit()
    # Generate and store OTP
    otp = str(random.randint(100000, 999999))
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    expires_at = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO email_otps (user_id, otp_hash, expires_at, verified) VALUES (?, ?, ?, 0)",
              (user_id, otp_hash, expires_at))
    conn.commit()
    conn.close()
    session.permanent = True
    session["user_id"] = user_id
    try:
        send_otp_email(email, name, otp)
    except Exception as e:
        print(f"[OTP] Send failed on register: {e}")
    try:
        send_welcome_email(email, name)
    except Exception as e:
        print(f"[EMAIL] Welcome email failed: {e}")
    return jsonify({"message": "Registration successful", "redirect": "/verify-email"}), 201
# =====================
# COURSES PAGE
# =====================
@app.route("/courses")
def courses_page():
    if "user_id" not in session:
        return redirect("/login-page")
    if is_admin(session["user_id"]):
        return redirect("/admin")
    access = get_access_state(session["user_id"])
    if access["state"] == "unverified":
        return redirect("/verify-email")
    return render_template("courses.html")
@app.route("/api/courses/search")
def search_courses():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    query = request.args.get("q", "").strip().lower()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT level, semester FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "User not found"}), 404
    user_level = int(user["level"])
    user_semester = user["semester"]
    eligible_levels = [str(lvl) for lvl in [300, 400, 500] if lvl <= user_level]
    placeholders = ",".join("?" for _ in eligible_levels)
    params = eligible_levels + [user_semester]
    if query:
        sql = f"""SELECT id, course_code, course_title, level, semester FROM courses
                  WHERE level IN ({placeholders}) AND semester=?
                  AND (LOWER(course_code) LIKE ? OR LOWER(course_title) LIKE ?)
                  ORDER BY level ASC, id DESC"""
        params += [f"%{query}%", f"%{query}%"]
    else:
        sql = f"""SELECT id, course_code, course_title, level, semester FROM courses
                  WHERE level IN ({placeholders}) AND semester=?
                  ORDER BY level ASC, id DESC"""
    c.execute(sql, params)
    results = c.fetchall()
    conn.close()
    return jsonify({
        "courses": [{
            "id": r["id"], "code": r["course_code"], "title": r["course_title"],
            "level": r["level"], "semester": r["semester"],
            "is_own_level": r["level"] == user["level"]
        } for r in results],
        "user_level": str(user_level),
        "user_semester": user_semester
    })
@app.route("/api/courses/my")
def my_courses():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    data = get_user_accessible_courses(session["user_id"])
    if not data:
        return jsonify({"error": "User not found"}), 404
    main = [{"id": r["id"], "code": r["course_code"], "title": r["course_title"], "type": "main"}
            for r in data["main_courses"]]
    rerun = []
    for lvl, courses in data["rerun_courses"].items():
        for r in courses:
            rerun.append({"id": r["id"], "code": r["course_code"],
                          "title": r["course_title"], "type": "rerun", "rerun_level": lvl})
    return jsonify({"main_paid": data["main_paid"], "courses": main, "rerun_courses": rerun})
def get_user_accessible_courses(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT level, semester FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    if not user:
        conn.close()
        return None
    # FIX: normalize level/semester before querying. Strict "=" matching was
    # silently returning zero rows whenever stored values had extra whitespace
    # or mismatched types (e.g. level "400" vs " 400", semester as text vs int).
    user_level = str(user["level"]).strip()
    try:
        user_semester = int(str(user["semester"]).strip())
    except (TypeError, ValueError):
        user_semester = user["semester"]
    c.execute("SELECT status, admin_override_status FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,))
    payment = c.fetchone()
    main_paid = payment and (payment["status"] == "paid" or payment["admin_override_status"] == "paid")
    # FIX: TRIM() + normalized params so stray whitespace in stored course rows
    # no longer causes a silent empty result.
    c.execute("""SELECT id, course_code, course_title, description, level, semester
                 FROM courses
                 WHERE TRIM(level)=? AND semester=?
                 ORDER BY id DESC""",
              (user_level, user_semester))
    main_courses = c.fetchall()
    c.execute("SELECT rerun_level, status, admin_override_status FROM rerun_passes WHERE user_id=?", (user_id,))
    passes = c.fetchall()
    rerun_courses = {}
    for p in passes:
        effective = p["admin_override_status"] if p["admin_override_status"] else p["status"]
        if effective == "paid":
            lvl = p["rerun_level"]
            c.execute("""SELECT id, course_code, course_title, description, level, semester
                         FROM courses
                         WHERE TRIM(level)=? AND semester=?
                         ORDER BY id DESC""",
                      (str(lvl).strip(), user_semester))
            rerun_courses[lvl] = c.fetchall()
    conn.close()
    return {"user": user, "main_paid": main_paid, "main_courses": main_courses, "rerun_courses": rerun_courses}
# =====================
# COURSE PAGE — access decision enforced
# =====================
@app.route("/course/<int:course_id>")
def course_page(course_id):
    if "user_id" not in session:
        return redirect("/login-page")
    if is_admin(session["user_id"]):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM courses WHERE id=?", (course_id,))
        course = c.fetchone()
        c.execute("SELECT * FROM materials WHERE course_id=? AND file_type='audio'", (course_id,))
        audios = c.fetchall()
        c.execute("SELECT * FROM materials WHERE course_id=? AND file_type='pdf'", (course_id,))
        pdfs = c.fetchall()
        conn.close()
        if not course: abort(404)
        return render_template("course.html", course=course, audios=audios, pdfs=pdfs, is_rerun=False)
    access = get_access_state(session["user_id"])
    if access["state"] == "unverified":
        return redirect("/verify-email")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT level, semester FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    c.execute("SELECT * FROM courses WHERE id=?", (course_id,))
    course = c.fetchone()
    if not course:
        conn.close()
        abort(404)
    has_access = False
    is_rerun = False
    if access["state"] == "paid":
        # Full access — check level/semester match or rerun pass
        if course["level"] == user["level"] and course["semester"] == user["semester"]:
            has_access = True
        elif course["semester"] == user["semester"] and int(course["level"]) < int(user["level"]):
            c.execute("""SELECT status, admin_override_status FROM rerun_passes
                         WHERE user_id=? AND rerun_level=? ORDER BY id DESC LIMIT 1""",
                      (session["user_id"], course["level"]))
            rpass = c.fetchone()
            if rpass and (rpass["status"] == "paid" or rpass["admin_override_status"] == "paid"):
                has_access = True
                is_rerun = True
    elif access["state"] == "trial":
        # Trial — only the course flagged is_trial for this user's level+semester
        trial_id = access.get("trial_course_id")
        if trial_id and str(course_id) == str(trial_id):
            has_access = True
    if not has_access:
        conn.close()
        if access["state"] in ("trial", "trial_expired"):
            trial_course = access.get("trial_course") if access["state"] == "trial" else get_trial_course_for(user["level"], user["semester"])
            return render_template("payment_wall.html", course=course,
                                   is_trial=(access["state"] == "trial"),
                                   trial_course_id=trial_course["id"] if trial_course else None)
        return redirect("/account")
    c.execute("SELECT * FROM materials WHERE course_id=? AND file_type='audio'", (course_id,))
    audios = c.fetchall()
    c.execute("SELECT * FROM materials WHERE course_id=? AND file_type='pdf'", (course_id,))
    pdfs = c.fetchall()
    conn.close()
    return render_template("course.html", course=course, audios=audios, pdfs=pdfs, is_rerun=is_rerun)
# =====================
# PDF VIEWER
# =====================
@app.route("/course/<int:course_id>/pdf/<int:material_id>")
def pdf_viewer(course_id, material_id):
    if "user_id" not in session:
        return redirect("/login-page")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT level, semester FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    c.execute("SELECT * FROM courses WHERE id=?", (course_id,))
    course = c.fetchone()
    if not course:
        conn.close()
        abort(404)
    access = get_access_state(session["user_id"])
    has_access = False
    if is_admin(session["user_id"]):
        has_access = True
    elif access["state"] == "paid":
        if course["level"] == user["level"] and course["semester"] == user["semester"]:
            has_access = True
        elif course["semester"] == user["semester"] and int(course["level"]) < int(user["level"]):
            c.execute("""SELECT status, admin_override_status FROM rerun_passes
                         WHERE user_id=? AND rerun_level=? ORDER BY id DESC LIMIT 1""",
                      (session["user_id"], course["level"]))
            rpass = c.fetchone()
            if rpass and (rpass["status"] == "paid" or rpass["admin_override_status"] == "paid"):
                has_access = True
    elif access["state"] == "trial":
        trial_id = access.get("trial_course_id")
        if trial_id and str(course_id) == str(trial_id):
            has_access = True
    if not has_access:
        conn.close()
        return redirect("/account")
    c.execute("SELECT id, filename FROM materials WHERE id=? AND course_id=? AND file_type='pdf'",
              (material_id, course_id))
    material = c.fetchone()
    conn.close()
    if not material: abort(404)
    supabase_url = get_material_url(material["filename"])
    if not supabase_url: abort(404)
    return render_template("pdf_viewer.html", course_id=course_id,
                           material_id=material["id"], supabase_url=supabase_url)
# =====================
# SUPABASE URL HELPER
# =====================
def get_material_url(filename):
    LEGACY_FILES = {
        "Psy405_WideMindNotes.pdf": "https://rtdshzvyzuzqndddxnkv.supabase.co/storage/v1/object/public/materials/Psy405_WideMindNotes%20(1).pdf",
        "Psy429_WideMindNotes.pdf": "https://rtdshzvyzuzqndddxnkv.supabase.co/storage/v1/object/public/materials/Psy429_WideMindNotes%20(1).pdf",
        "Psy494_WideMindNotes.pdf": "https://rtdshzvyzuzqndddxnkv.supabase.co/storage/v1/object/public/materials/Psy494_WideMindNotes%20(1).pdf",
        "Psy429_Session_1-5.mp3": "https://rtdshzvyzuzqndddxnkv.supabase.co/storage/v1/object/public/materials/Psy429-Session-1-5.MP3",
    }
    if filename in LEGACY_FILES:
        return LEGACY_FILES[filename]
    from urllib.parse import quote
    return f"https://rtdshzvyzuzqndddxnkv.supabase.co/storage/v1/object/public/materials/{quote(filename)}"
# =====================
# STREAM — access check
# =====================
def check_course_access(user_id, course_id):
    access = get_access_state(user_id)
    if access["state"] == "paid":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT level, semester FROM users WHERE id=?", (user_id,))
        user = c.fetchone()
        c.execute("SELECT level, semester FROM courses WHERE id=?", (course_id,))
        course = c.fetchone()
        if not user or not course:
            conn.close()
            return False
        if course["level"] == user["level"] and course["semester"] == user["semester"]:
            conn.close()
            return True
        if course["semester"] == user["semester"] and int(course["level"]) < int(user["level"]):
            c.execute("""SELECT status, admin_override_status FROM rerun_passes
                         WHERE user_id=? AND rerun_level=? ORDER BY id DESC LIMIT 1""",
                      (user_id, course["level"]))
            rpass = c.fetchone()
            conn.close()
            return bool(rpass and (rpass["status"] == "paid" or rpass["admin_override_status"] == "paid"))
        conn.close()
        return False
    elif access["state"] == "trial":
        trial_id = access.get("trial_course_id")
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT course_id FROM materials WHERE id=? LIMIT 1", (course_id,))
        conn.close()
        return trial_id and str(course_id) == str(trial_id)
    return False
@app.route("/stream/audio/<int:material_id>")
def stream_audio(material_id):
    if "user_id" not in session: abort(403)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT course_id, filename FROM materials WHERE id=? AND file_type='audio'", (material_id,))
    material = c.fetchone()
    conn.close()
    if not material: abort(404)
    if not is_admin(session["user_id"]) and not check_course_access(session["user_id"], material["course_id"]):
        abort(403)
    url = get_material_url(material["filename"])
    if not url: abort(404)
    return redirect(url)
@app.route("/stream/pdf/<int:material_id>")
def stream_pdf(material_id):
    if "user_id" not in session: abort(403)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT course_id, filename FROM materials WHERE id=? AND file_type='pdf'", (material_id,))
    material = c.fetchone()
    conn.close()
    if not material: abort(404)
    if not is_admin(session["user_id"]) and not check_course_access(session["user_id"], material["course_id"]):
        abort(403)
    url = get_material_url(material["filename"])
    if not url: abort(404)
    return redirect(url)
# =====================
# NOTIFICATIONS
# =====================
@app.route("/api/notifications")
def get_notifications():
    if "user_id" not in session: return jsonify([])
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM notifications WHERE user_id=? AND is_archived=0 ORDER BY created_at DESC",
              (session["user_id"],))
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])
@app.route("/api/notifications/read/<int:notif_id>", methods=["POST"])
def mark_notification_read(notif_id):
    if "user_id" not in session: return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (notif_id, session["user_id"]))
    conn.commit()
    conn.close()
    return jsonify({"success": True})
@app.route("/payment-success")
def payment_success(): return render_template("payment_success.html")
@app.route("/api/contact", methods=["POST"])
def submit_contact():
    user_id = session.get("user_id")
    if not user_id: return jsonify({"redirect": "/login-page"}), 200
    if is_admin(user_id): return jsonify({"error": "Admins cannot send contact messages"}), 200
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    subject = data.get("subject", "").strip()
    message = data.get("message", "").strip()
    if not name or not email or not message:
        return jsonify({"error": "All required fields must be filled"}), 400
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO contact_messages (name, email, subject, message) VALUES (?, ?, ?, ?)",
              (name, email, subject, message))
    conn.commit()
    conn.close()
    return jsonify({"message": "Message sent successfully"}), 201
@app.route("/settings")
def settings():
    if "user_id" not in session: return redirect("/login-page")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name, email, level, semester FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    c.execute("""SELECT COALESCE(p.admin_override_status, p.status) AS status
                 FROM payments p WHERE p.user_id=? ORDER BY p.id DESC LIMIT 1""",
              (session["user_id"],))
    payment = c.fetchone()
    conn.close()
    payment_status = payment["status"] if payment else "unpaid"
    return render_template("settings.html", user=user, payment_status=payment_status)
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login-page")
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    socketio.run(app, host="0.0.0.0", port=port)