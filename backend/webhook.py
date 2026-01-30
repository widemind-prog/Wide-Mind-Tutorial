from flask import Blueprint, request, jsonify
import hmac
import hashlib
import os
from backend.db import get_db

webhook_bp = Blueprint("webhook_bp", __name__)

@webhook_bp.route("/webhook/paystack", methods=["POST"])
def paystack_webhook():
    paystack_secret = os.environ.get("PAYSTACK_SECRET_KEY")
    signature = request.headers.get("X-Paystack-Signature")
    payload = request.get_data()

    if not paystack_secret or not signature:
        return "Unauthorized", 401

    # 🔐 Verify Paystack signature
    computed_hash = hmac.new(
        paystack_secret.encode("utf-8"),
        payload,
        hashlib.sha512
    ).hexdigest()

    if signature != computed_hash:
        return "Unauthorized", 401

    event = request.json

    if event.get("event") != "charge.success":
        return jsonify({"status": "ignored"}), 200

    data = event.get("data", {})
    customer = data.get("customer", {})

    email = customer.get("email")
    reference = data.get("reference")
    amount = data.get("amount")  # kobo

    if not email or not reference or amount is None:
        return jsonify({"status": "invalid_payload"}), 200

    conn = get_db()
    c = conn.cursor()

    # 🔁 Prevent duplicate webhook processing (by reference)
    c.execute("SELECT id FROM payments WHERE reference = ?", (reference,))
    if c.fetchone():
        conn.close()
        return jsonify({"status": "duplicate"}), 200

    # 🔍 Get user id
    c.execute("SELECT id FROM users WHERE email = ?", (email,))
    user = c.fetchone()

    if not user:
        conn.close()
        return jsonify({"status": "user_not_found"}), 200

    user_id = user["id"]

    # 🔍 Get existing payment record
    c.execute("""
    SELECT *
    FROM payments
    WHERE user_id = ?
    ORDER BY id DESC
    LIMIT 1
""", (user_id,))
payment = c.fetchone()

    # 🧠 RULES:
    # - admin_override_status = unpaid → NEVER mark paid
    # - admin_override_status = paid → already paid, do nothing
    # - no override → can mark paid ONLY if status is unpaid

    if not payment:
        # No record → create paid record
        c.execute("""
            INSERT INTO payments (user_id, amount, status, reference, paid_at)
            VALUES (?, ?, 'paid', ?, datetime('now'))
        """, (user_id, amount, reference))

    elif payment["admin_override_status"] == "unpaid":
        # 🚫 Admin explicitly blocked payment
        conn.close()
        return jsonify({"status": "blocked_by_admin"}), 200

    elif payment["admin_override_status"] == "paid":
        # ✅ Admin already approved
        conn.close()
        return jsonify({"status": "admin_paid"}), 200

    elif payment["status"] == "unpaid":
        # ✅ Normal Paystack success → mark paid
        c.execute("""
            UPDATE payments
            SET status='paid',
                reference=?,
                paid_at=datetime('now')
            WHERE user_id=? AND status='unpaid'
        """, (reference, user_id))

    # else: already paid → do nothing

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"}), 200