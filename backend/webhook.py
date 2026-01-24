from flask import Blueprint, request, jsonify
import hmac
import hashlib
from backend.db import get_db
import os

webhook_bp = Blueprint("webhook_bp", __name__)

@webhook_bp.route("/webhook/paystack", methods=["POST"])
def paystack_webhook():
    paystack_secret = os.environ.get("PAYSTACK_SECRET_KEY")
    signature = request.headers.get("X-Paystack-Signature")
    payload = request.get_data()

    if not paystack_secret or not signature:
        return "Unauthorized", 401

    # Verify signature
    computed_hash = hmac.new(paystack_secret.encode("utf-8"), payload, hashlib.sha512).hexdigest()
    if signature != computed_hash:
        return "Unauthorized", 401

    event = request.json

    if event.get("event") == "charge.success":
        data = event.get("data", {})
        customer_info = data.get("customer", {})
        email = customer_info.get("email")
        ref = data.get("reference")
        amount = data.get("amount")  # in kobo

        if not email or not ref or amount is None:
            return jsonify({"status": "invalid_payload"}), 200

        conn = get_db()
        c = conn.cursor()

        # Prevent duplicate webhook
        c.execute("SELECT id FROM payments WHERE reference = ?", (ref,))
        if c.fetchone():
            conn.close()
            return jsonify({"status": "duplicate"}), 200

        # Get current payment
        c.execute("SELECT status, admin_override_status FROM payments WHERE user_id=(SELECT id FROM users WHERE email=?)", (email,))
        payment = c.fetchone()

        # Only mark paid if currently unpaid (default or admin marked unpaid)
        if not payment:
            # Create new record
            c.execute("""
                INSERT INTO payments (user_id, amount, status, reference, paid_at)
                VALUES ((SELECT id FROM users WHERE email=?), ?, 'paid', ?, datetime('now'))
            """, (email, amount, ref))
        elif payment["admin_override_status"] == "unpaid" or (not payment["admin_override_status"] and payment["status"] == "unpaid"):
            c.execute("""
                UPDATE payments
                SET status='paid', reference=?, paid_at=datetime('now')
                WHERE user_id=(SELECT id FROM users WHERE email=?)
            """, (ref, email))
        # Else admin has absolute control, do nothing

        conn.commit()
        conn.close()

    return jsonify({"status": "ok"}), 200