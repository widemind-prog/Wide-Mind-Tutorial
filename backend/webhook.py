from flask import Blueprint, request, jsonify
import hmac
import hashlib
from backend.db import get_db
import os

webhook_bp = Blueprint("webhook_bp", __name__)

@webhook_bp.route("/webhook/paystack", methods=["POST"])
def paystack_webhook():
    paystack_secret = os.environ.get("PAYSTACK_SECRET_KEY")
    hash = request.headers.get("X-Paystack-Signature")
    payload = request.get_data()

    # Verify signature
    computed_hash = hmac.new(paystack_secret.encode(), payload, hashlib.sha512).hexdigest()
    if hash != computed_hash:
        return "Unauthorized", 401

    event = request.json
    if event["event"] == "charge.success":
        # Get email
        email = event["data"]["customer"]["email"]
        conn = get_db()
        c = conn.cursor()
        # Mark user's payment as paid
        c.execute("UPDATE payments SET status='paid' WHERE user_id=(SELECT id FROM users WHERE email=?)", (email,))
        conn.commit()
        conn.close()

    return jsonify({"status": "ok"})
    
    ref = event["data"]["reference"]

c.execute("SELECT reference FROM payments WHERE reference=?", (ref,))
if c.fetchone():
    return jsonify({"status": "duplicate"}), 200

c.execute("""
    UPDATE payments
    SET status='paid', reference=?
    WHERE user_id=(SELECT id FROM users WHERE email=?)
""", (ref, email))
