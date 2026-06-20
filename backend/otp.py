from flask import Blueprint, jsonify, session, request
from backend.db import get_db
from backend.email_service import send_otp_email
import hashlib
import random
from datetime import datetime, timedelta

otp_bp = Blueprint("otp_bp", __name__)

def _hash_otp(otp): return hashlib.sha256(str(otp).encode()).hexdigest()

def _generate_otp(): return str(random.randint(100000, 999999))

# =====================
# SEND / RESEND OTP
# =====================
@otp_bp.route("/api/otp/send", methods=["POST"])
def send_otp():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    conn = get_db()
    c = conn.cursor()

    # Enforce 60-second cooldown
    c.execute("""
        SELECT created_at FROM email_otps
        WHERE user_id=? ORDER BY id DESC LIMIT 1
    """, (session["user_id"],))
    last = c.fetchone()
    if last and last["created_at"]:
        try:
            last_time = datetime.strptime(last["created_at"], "%Y-%m-%d %H:%M:%S")
            elapsed = (datetime.utcnow() - last_time).total_seconds()
            if elapsed < 60:
                conn.close()
                return jsonify({"error": f"Please wait {int(60 - elapsed)} seconds before resending"}), 429
        except Exception:
            pass

    # Get user email
    c.execute("SELECT email, name FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "User not found"}), 404

    otp = _generate_otp()
    otp_hash = _hash_otp(otp)
    expires_at = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

    # Delete old OTPs for this user, insert fresh one
    c.execute("DELETE FROM email_otps WHERE user_id=?", (session["user_id"],))
    c.execute("""
        INSERT INTO email_otps (user_id, otp_hash, expires_at, verified)
        VALUES (?, ?, ?, 0)
    """, (session["user_id"], otp_hash, expires_at))
    conn.commit()
    conn.close()

    try:
        send_otp_email(user["email"], user["name"], otp)
    except Exception as e:
        print(f"[OTP] Email failed: {e}")
        return jsonify({"error": "Failed to send OTP email. Please try again."}), 500

    return jsonify({"message": "OTP sent to your email"}), 200


# =====================
# VERIFY OTP
# =====================
@otp_bp.route("/api/otp/verify", methods=["POST"])
def verify_otp():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.get_json() or {}
    otp_input = str(data.get("otp", "")).strip()

    if not otp_input or len(otp_input) != 6:
        return jsonify({"error": "Enter the 6-digit OTP"}), 400

    otp_hash = _hash_otp(otp_input)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT id, expires_at, verified FROM email_otps
        WHERE user_id=? AND otp_hash=?
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"], otp_hash))
    record = c.fetchone()

    if not record:
        conn.close()
        return jsonify({"error": "Invalid OTP"}), 400

    if record["verified"]:
        conn.close()
        return jsonify({"error": "OTP already used"}), 400

    if now > record["expires_at"]:
        conn.close()
        return jsonify({"error": "OTP has expired. Request a new one."}), 400

    # Mark OTP used, verify user, start trial
    c.execute("UPDATE email_otps SET verified=1 WHERE id=?", (record["id"],))
    c.execute("""
        UPDATE users
        SET is_verified=1,
            trial_started_at=datetime('now')
        WHERE id=?
    """, (session["user_id"],))
    conn.commit()
    conn.close()

    return jsonify({"message": "Email verified!", "redirect": "/account"}), 200
