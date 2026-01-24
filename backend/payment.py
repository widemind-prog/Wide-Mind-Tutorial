from flask import Blueprint, jsonify, session, redirect
import requests
import os
from backend.db import get_db

payment_bp = Blueprint("payment_bp", __name__)

# ------------------------------------
# INIT PAYSTACK PAYMENT
# ------------------------------------
@payment_bp.route("/api/payment/init", methods=["POST"])
def init_payment():
    """
    Initialize Paystack payment for the logged-in user.
    """
    if "user_id" not in session:
        return jsonify({"status": False, "message": "Not authenticated"}), 401

    user_id = session["user_id"]

    # ₦100 in kobo
    amount = 10 * 100  # 10000 kobo

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
        return jsonify(
            {"status": False, "message": "Failed to initialize payment"},
            500
        )

    if resp_json.get("status"):
        return jsonify({"status": True, "data": resp_json["data"]})

    return jsonify({
        "status": False,
        "message": resp_json.get("message", "Payment initialization failed")
    })


# ------------------------------------
# PAYSTACK CALLBACK (REDIRECT ONLY)
# ------------------------------------
@payment_bp.route("/payment/callback", methods=["GET"])
def payment_callback():
    """
    Paystack redirects here after payment.
    Webhook handles confirmation.
    """
    return redirect("/account?payment=callback")


# ------------------------------------
# PAYMENT STATUS (USED BY ACCOUNT PAGE)
# ------------------------------------
@payment_bp.route("/api/payment/status", methods=["GET"])
def payment_status():
    if "user_id" not in session:
        return jsonify({"status": "unauthorized"}), 401

    user_id = session["user_id"]

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT status FROM payments WHERE user_id=?",
        (user_id,)
    )
    payment = c.fetchone()
    conn.close()

    if not payment:
        return jsonify({"status": "unpaid"})

    return jsonify({"status": payment["status"]})