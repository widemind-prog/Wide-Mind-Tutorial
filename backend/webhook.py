print(">>> webhook.py imported")

from flask import Blueprint, request, jsonify
import hmac
import hashlib
import os
from datetime import datetime
from backend.db import get_db

# ---------------------
# BLUEPRINT
# ---------------------
webhook_bp = Blueprint("webhook_bp", __name__, url_prefix="/webhook")

# ---------------------
# PAYSTACK WEBHOOK
# ---------------------
@webhook_bp.route("/paystack", methods=["POST"])
def paystack_webhook():
    """
    Handle Paystack webhook for successful payments.
    Updates user's payment status in DB and prevents replay attacks.
    """
    # ✅ Ensure secret is configured
    paystack_secret = os.environ.get("PAYSTACK_SECRET_KEY")
    if not paystack_secret:
        return "Server misconfigured", 500

    # ✅ Get signature and raw payload
    received_signature = request.headers.get("X-Paystack-Signature")
    payload = request.get_data()

    # ✅ Verify signature
    computed_signature = hmac.new(
        paystack_secret.encode(),
        payload,
        hashlib.sha512
    ).hexdigest()

    if received_signature != computed_signature:
        return "Unauthorized", 401

    # ✅ Parse event safely
    try:
        event = request.json
        event_type = event.get("event")
        event_data = event.get("data", {})
        customer = event_data.get("customer", {})
        email = customer.get("email")
        reference = event_data.get("reference")
    except Exception:
        return "Malformed payload", 400

    # ✅ Handle successful charge
    if event_type == "charge.success" and email and reference:
        now = datetime.utcnow().isoformat()
        conn = get_db()
        c = conn.cursor()

        # Prevent replay (duplicate reference)
        c.execute("SELECT reference FROM payments WHERE reference=?", (reference,))
        if c.fetchone():
            conn.close()
            return jsonify({"status": "duplicate"}), 200

        # Update payment status to paid
        c.execute("""
            UPDATE payments
            SET status='paid', reference=?, paid_at=?
            WHERE user_id=(SELECT id FROM users WHERE email=?)
        """, (reference, now, email))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok"}), 200

    return jsonify({"status": "ignored"}), 200