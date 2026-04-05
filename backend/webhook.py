from flask import Blueprint, request, jsonify
import hmac
import hashlib
import os
from backend.db import get_db, get_main_price, get_unlock_price
from backend.email_service import send_payment_success_email

webhook_bp = Blueprint("webhook_bp", __name__)

@webhook_bp.route("/webhook/paystack", methods=["POST"])
def paystack_webhook():
    paystack_secret = os.environ.get("PAYSTACK_SECRET_KEY")
    signature = request.headers.get("X-Paystack-Signature")
    payload = request.get_data()

    if not paystack_secret or not signature:
        return "Unauthorized", 401

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
    amount = data.get("amount")
    metadata = data.get("metadata", {})
    payment_type = metadata.get("payment_type", "main")

    if not email or not reference or amount is None:
        return jsonify({"status": "invalid_payload"}), 200

    # -----------------------------------------------
    # ROUTE TO CORRECT HANDLER
    # -----------------------------------------------
    if payment_type == "level_unlock":
        target_level = str(metadata.get("target_level", ""))
        return _handle_unlock_webhook(email, reference, amount, target_level)
    else:
        return _handle_main_webhook(email, reference, amount)


def _handle_main_webhook(email, reference, amount):
    """Handle main subscription payment confirmation."""
    conn = get_db()
    c = conn.cursor()

    # Deduplicate
    c.execute("SELECT id FROM payments WHERE reference=?", (reference,))
    if c.fetchone():
        conn.close()
        return jsonify({"status": "duplicate"}), 200

    c.execute("SELECT id, name, level FROM users WHERE email=?", (email,))
    user = c.fetchone()
    if not user:
        conn.close()
        return jsonify({"status": "user_not_found"}), 200

    user_id = user["id"]
    user_name = user["name"]
    user_level = str(user["level"]) if user["level"] else "400"

    # Validate amount
    expected = get_main_price(user_level)
    if amount != expected:
        conn.close()
        return jsonify({"status": "invalid_amount"}), 200

    c.execute("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,))
    payment = c.fetchone()
    paid_now = False

    if not payment:
        c.execute("""
            INSERT INTO payments (user_id, amount, status, reference, paid_at)
            VALUES (?, ?, 'paid', ?, datetime('now'))
        """, (user_id, amount, reference))
        paid_now = True
    elif payment["admin_override_status"] == "unpaid":
        conn.close()
        return jsonify({"status": "blocked_by_admin"}), 200
    elif payment["admin_override_status"] == "paid":
        conn.close()
        return jsonify({"status": "admin_paid"}), 200
    elif payment["status"] == "unpaid":
        c.execute("""
            UPDATE payments SET status='paid', reference=?, paid_at=datetime('now')
            WHERE user_id=? AND status='unpaid'
        """, (reference, user_id))
        paid_now = True

    conn.commit()
    conn.close()

    if paid_now:
        try:
            send_payment_success_email(email, user_name)
        except Exception as e:
            print("Webhook main payment email failed:", e)

    return jsonify({"status": "ok"}), 200


def _handle_unlock_webhook(email, reference, amount, target_level):
    """Handle level unlock payment confirmation."""
    if target_level not in ["200", "300"]:
        return jsonify({"status": "invalid_target_level"}), 200

    conn = get_db()
    c = conn.cursor()

    # Deduplicate
    c.execute("SELECT id FROM level_unlocks WHERE reference=?", (reference,))
    if c.fetchone():
        conn.close()
        return jsonify({"status": "duplicate"}), 200

    c.execute("SELECT id, name, level FROM users WHERE email=?", (email,))
    user = c.fetchone()
    if not user:
        conn.close()
        return jsonify({"status": "user_not_found"}), 200

    user_id = user["id"]
    user_name = user["name"]
    buyer_level = str(user["level"]) if user["level"] else "400"

    # Validate amount
    expected = get_unlock_price(buyer_level, target_level)
    if not expected or amount != expected:
        conn.close()
        return jsonify({"status": "invalid_amount"}), 200

    c.execute("""
        SELECT * FROM level_unlocks
        WHERE user_id=? AND target_level=?
        ORDER BY id DESC LIMIT 1
    """, (user_id, target_level))
    existing = c.fetchone()
    paid_now = False

    if not existing:
        c.execute("""
            INSERT INTO level_unlocks (user_id, target_level, amount, status, reference, paid_at)
            VALUES (?, ?, ?, 'paid', ?, datetime('now'))
        """, (user_id, target_level, amount, reference))
        paid_now = True
    elif existing["admin_override_status"] == "unpaid":
        conn.close()
        return jsonify({"status": "blocked_by_admin"}), 200
    elif existing["admin_override_status"] == "paid":
        conn.close()
        return jsonify({"status": "already_paid"}), 200
    elif existing["status"] == "unpaid":
        c.execute("""
            UPDATE level_unlocks
            SET status='paid', reference=?, paid_at=datetime('now')
            WHERE id=?
        """, (reference, existing["id"]))
        paid_now = True

    conn.commit()
    conn.close()

    if paid_now:
        try:
            send_payment_success_email(email, user_name)
        except Exception as e:
            print("Webhook unlock payment email failed:", e)

    return jsonify({"status": "ok"}), 200
