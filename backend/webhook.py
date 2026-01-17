from flask import Blueprint, request, jsonify
import hmac
import hashlib
from backend.db import get_db
import os
from datetime import datetime

webhook_bp = Blueprint("webhook_bp", __name__)

@webhook_bp.route("/webhook/paystack", methods=["POST"])
def paystack_webhook():
    paystack_secret = os.environ.get("PAYSTACK_SECRET_KEY")
    hash = request.headers.get("X-Paystack-Signature")
    payload = request.get_data()

    # Verify signature
    computed_hash = hmac.new(
        paystack_secret.encode(),
        payload,
        hashlib.sha512
    ).hexdigest()

    if hash != computed_hash:
        return "Unauthorized", 401

    event = request.json

    if event["event"] == "charge.success":
        email = event["data"]["customer"]["email"]
        ref = event["data"]["reference"]
        now = datetime.utcnow().isoformat()

        conn = get_db()
        c = conn.cursor()

        # Prevent replay (duplicate reference)
        c.execute("SELECT reference FROM payments WHERE reference=?", (ref,))
        if c.fetchone():
            conn.close()
            return jsonify({"status": "duplicate"}), 200

        # Mark user's payment as paid and record timestamp
        c.execute("""
            UPDATE payments
            SET status='paid', reference=?, paid_at=?
            WHERE user_id=(SELECT id FROM users WHERE email=?)
        """, (ref, now, email))

        conn.commit()
        conn.close()

    return jsonify({"status": "ok"}), 200