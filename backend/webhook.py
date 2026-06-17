from flask import Blueprint, request, jsonify
from backend.db import get_db
import hashlib, hmac, os, json

webhook_bp = Blueprint("webhook_bp", __name__)

LEVEL_AMOUNTS = {"300": 1026375, "400": 1533042, "500": 2041025}
RERUN_AMOUNTS = {"300": 359231, "400": 536565}

@webhook_bp.route("/api/webhook/paystack", methods=["POST"])
def paystack_webhook():
    secret = os.environ.get("PAYSTACK_SECRET_KEY", "")
    sig = request.headers.get("X-Paystack-Signature", "")
    body = request.get_data()

    expected = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return jsonify({"error": "Invalid signature"}), 400

    payload = json.loads(body)
    event = payload.get("event")
    data = payload.get("data", {})

    if event == "charge.success":
        email = data.get("customer", {}).get("email")
        amount_paid = data.get("amount", 0)
        reference = data.get("reference")
        meta = data.get("metadata", {})
        payment_type = meta.get("payment_type", "main")
        rerun_level = str(meta.get("rerun_level", ""))

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, level FROM users WHERE email=?", (email,))
        user = c.fetchone()

        if not user:
            conn.close()
            return jsonify({"status": "user not found"}), 200

        if payment_type == "rerun" and rerun_level in ("300", "400"):
            expected_amount = RERUN_AMOUNTS.get(rerun_level, 0)
            if amount_paid >= expected_amount:
                c.execute("""
                    UPDATE rerun_passes
                    SET status='paid', reference=?, paid_at=datetime('now')
                    WHERE user_id=? AND rerun_level=?
                """, (reference, user["id"], rerun_level))
                conn.commit()
        else:
            expected_amount = LEVEL_AMOUNTS.get(str(user["level"]), 0)
            if amount_paid >= expected_amount:
                c.execute("""
                    UPDATE payments SET status='paid', reference=?, paid_at=datetime('now')
                    WHERE user_id=?
                """, (reference, user["id"]))
                conn.commit()

        conn.close()

    return jsonify({"status": "ok"}), 200
