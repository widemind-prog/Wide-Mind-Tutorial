from flask import Blueprint, jsonify, session, redirect, request
import requests
import os
from backend.db import get_db, is_admin

payment_bp = Blueprint("payment_bp", __name__)

# ------------------------------------
# INIT PAYSTACK PAYMENT
# ------------------------------------
@payment_bp.route("/api/payment/init", methods=["POST"])
def init_payment():
    if "user_id" not in session:
        return jsonify({"status": False, "message": "Not authenticated"}), 401

    user_id = session["user_id"]

    if is_admin(user_id):
        return jsonify({"status": True, "message": "Admin does not require payment"}), 200

    amount = 100 * 100  # 10000 kobo

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    conn.close()

    if not user:
        return jsonify({"status": False, "message": "User not found"}), 404

    headers = {
        "Authorization": f"Bearer {os.environ.get('PAYSTACK_SECRET_KEY')}",
        "Content-Type": "application/json"
    }

    payload = {
        "email": user["email"],
        "amount": amount,
        "callback_url": "https://wide-mind-tutorial-gptu.onrender.com/payment/callback"
    }

    try:
        resp = requests.post(
            "https://api.paystack.co/transaction/initialize",
            json=payload,
            headers=headers
        )
        resp.raise_for_status()
        resp_json = resp.json()
    except requests.RequestException:
        return jsonify({"status": False, "message": "Failed to initialize payment"}), 500

    if resp_json.get("status"):
        return jsonify({"status": True, "data": resp_json["data"]})

    return jsonify({"status": False, "message": resp_json.get("message", "Payment initialization failed")})

# ------------------------------------
# PAYSTACK CALLBACK
# ------------------------------------
@payment_bp.route("/payment/callback", methods=["GET"])
def payment_callback():
    reference = request.args.get("reference")
    if not reference:
        return redirect("/account?payment=failed")

    headers = {"Authorization": f"Bearer {os.environ.get('PAYSTACK_SECRET_KEY')}"}

    try:
        resp = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers=headers)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return redirect("/account?payment=failed")

    if data.get("status") and data["data"]["status"] == "success":
        email = data["data"]["customer"]["email"]
        amount = data["data"]["amount"]

        if amount != 10000:
            return redirect("/account?payment=invalid_amount")

        conn = get_db()
        c = conn.cursor()

        # Get current payment
        c.execute("SELECT status, admin_override_status FROM payments WHERE user_id=(SELECT id FROM users WHERE email=?)", (email,))
        payment = c.fetchone()

        # Only mark paid if status is unpaid (default or admin marked unpaid)
        if not payment:
            # Create payment record
            c.execute("""
                INSERT INTO payments (user_id, amount, status, reference, paid_at)
                VALUES ((SELECT id FROM users WHERE email=?), ?, 'paid', ?, datetime('now'))
            """, (email, amount, reference))
        elif payment["admin_override_status"] == "unpaid" or (not payment["admin_override_status"] and payment["status"] == "unpaid"):
            c.execute("""
                UPDATE payments
                SET status='paid', reference=?, paid_at=datetime('now')
                WHERE user_id=(SELECT id FROM users WHERE email=?)
            """, (reference, email))
        # Otherwise, admin has paid, do not override

        conn.commit()
        conn.close()
        return redirect("/account?payment=success")
    else:
        return redirect("/account?payment=failed")

# ------------------------------------
# PAYMENT STATUS
# ------------------------------------
@payment_bp.route("/api/payment/status", methods=["GET"])
def payment_status():
    if "user_id" not in session:
        return jsonify({"status": "unauthorized"}), 401

    user_id = session["user_id"]

    if is_admin(user_id):
        return jsonify({"status": "admin", "amount": 0}), 200

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT status, reference, admin_override_status, amount FROM payments WHERE user_id=?", (user_id,))
    payment = c.fetchone()

    if not payment:
        # Default unpaid record
        c.execute("INSERT INTO payments (user_id, amount, status) VALUES (?, ?, ?)", (user_id, 100, "unpaid"))
        conn.commit()
        conn.close()
        return jsonify({"status": "unpaid", "amount": 100})

    # Admin override takes absolute precedence
    status = payment["admin_override_status"] if payment["admin_override_status"] else payment["status"]

    # Verify Paystack only if reference exists and current status is unpaid
    if payment.get("reference") and status == "unpaid":
        headers = {"Authorization": f"Bearer {os.environ.get('PAYSTACK_SECRET_KEY')}"}
        try:
            resp = requests.get(f"https://api.paystack.co/transaction/verify/{payment['reference']}", headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") and data["data"]["status"] == "success":
                # Update DB to paid if unpaid
                c.execute("UPDATE payments SET status='paid', paid_at=datetime('now') WHERE user_id=?", (user_id,))
                conn.commit()
                status = "paid"
        except requests.RequestException:
            pass

    conn.close()
    return jsonify({"status": status, "amount": payment["amount"]})