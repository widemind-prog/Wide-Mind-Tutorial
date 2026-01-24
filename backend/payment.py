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
    """
    Initialize Paystack payment for the logged-in user.
    """
    if "user_id" not in session:
        return jsonify({"status": False, "message": "Not authenticated"}), 401

    user_id = session["user_id"]

    # Admins don't need payment
    if is_admin(user_id):
        return jsonify({"status": True, "message": "Admin does not require payment"}), 200

    # ₦100 in kobo
    amount = 100 * 100  # 10000 kobo

    # Get user email from DB
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
# PAYSTACK CALLBACK (REDIRECT + VERIFY)
# ------------------------------------
@payment_bp.route("/payment/callback", methods=["GET"])
def payment_callback():
    """
    Paystack redirects here after payment.
    Verify payment via Paystack API and update DB.
    """
    reference = request.args.get("reference")
    if not reference:
        return redirect("/account?payment=failed")

    headers = {
        "Authorization": f"Bearer {os.environ.get('PAYSTACK_SECRET_KEY')}"
    }

    # Verify payment with Paystack
    try:
        resp = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return redirect("/account?payment=failed")

    if data.get("status") and data["data"]["status"] == "success":
        email = data["data"]["customer"]["email"]
        amount = data["data"]["amount"]

        # Only accept ₦100 payments (10000 kobo)
        if amount != 10000:
            return redirect("/account?payment=invalid_amount")

        # Update database
        conn = get_db()
        c = conn.cursor()
        # Prevent duplicate reference
        c.execute("SELECT reference FROM payments WHERE reference=?", (reference,))
        if not c.fetchone():
            c.execute("""
                UPDATE payments
                SET status='paid', reference=?
                WHERE user_id=(SELECT id FROM users WHERE email=?)
            """, (reference, email))
            conn.commit()
        conn.close()

        return redirect("/account?payment=success")
    else:
        return redirect("/account?payment=failed")


# ------------------------------------
# PAYMENT STATUS (USED BY ACCOUNT PAGE)
# ------------------------------------
@payment_bp.route("/api/payment/status", methods=["GET"])
def payment_status():
    if "user_id" not in session:
        return jsonify({"status": "unauthorized"}), 401

    user_id = session["user_id"]

    # Admin users don't require payment
    if is_admin(user_id):
        return jsonify({"status": "admin", "amount": 0}), 200

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT status, reference, amount FROM payments WHERE user_id=?",
        (user_id,)
    )
    payment = c.fetchone()

    # If no payment record, create default unpaid
    if not payment:
        c.execute(
            "INSERT INTO payments (user_id, amount, status) VALUES (?, ?, ?)",
            (user_id, 100, "unpaid")
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "unpaid", "amount": 100})

    # If there is a reference, verify it with Paystack
    payment_status = payment["status"]
    if payment["reference"]:
        headers = {
            "Authorization": f"Bearer {os.environ.get('PAYSTACK_SECRET_KEY')}"
        }
        try:
            resp = requests.get(
                f"https://api.paystack.co/transaction/verify/{payment['reference']}",
                headers=headers
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") and data["data"]["status"] == "success":
                # Update DB if not marked paid
                if payment["status"] != "paid":
                    c.execute("""
                        UPDATE payments
                        SET status='paid'
                        WHERE user_id=?
                    """, (user_id,))
                    conn.commit()
                payment_status = "paid"
            else:
                payment_status = "unpaid"
        except requests.RequestException:
            payment_status = payment["status"]

    conn.close()
    return jsonify({"status": payment_status, "amount": payment["amount"]})