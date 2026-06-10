from flask import Blueprint, jsonify, session, request, redirect, current_app
from backend.db import get_db, is_admin
import requests as req
import os

payment_bp = Blueprint("payment_bp", __name__)

LEVEL_AMOUNTS = {
    "300": 1026375,
    "400": 1533042,
    "500": 2041025,
}

def get_amount_for_level(level):
    return LEVEL_AMOUNTS.get(str(level), 1026375)

@payment_bp.route("/api/payment/init", methods=["POST"])
def init_payment():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT email, level FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "User not found"}), 404

    # Always use the correct amount for the user's current level
    amount = get_amount_for_level(user["level"])

    # Update payment record amount to match current level (in case of migration)
    c.execute(
        "UPDATE payments SET amount=? WHERE user_id=? AND status != 'paid' AND (admin_override_status IS NULL OR admin_override_status != 'paid')",
        (amount, session["user_id"])
    )
    conn.commit()
    conn.close()

    secret_key = current_app.config["PAYSTACK_SECRET_KEY"]
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "email": user["email"],
        "amount": amount,
        "callback_url": "https://www.widemindtutorial.com/api/payment/callback"
    }

    response = req.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    data = response.json()
    return jsonify(data)

@payment_bp.route("/api/payment/callback")
def payment_callback():
    reference = request.args.get("reference")
    if not reference:
        return redirect("/account?payment=failed")

    secret_key = current_app.config.get("PAYSTACK_SECRET_KEY")
    headers = {"Authorization": f"Bearer {secret_key}"}
    response = req.get(f"https://api.paystack.co/transaction/verify/{reference}", headers=headers)
    data = response.json()

    if data.get("data", {}).get("status") == "success":
        customer_email = data["data"]["customer"]["email"]
        amount_paid = data["data"]["amount"]

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, level FROM users WHERE email=?", (customer_email,))
        user = c.fetchone()

        if user:
            expected_amount = get_amount_for_level(user["level"])
            if amount_paid >= expected_amount:
                c.execute("""
                    UPDATE payments
                    SET status='paid', reference=?, paid_at=datetime('now')
                    WHERE user_id=?
                """, (reference, user["id"]))
                conn.commit()
        conn.close()

    return redirect("/account?payment=callback")

@payment_bp.route("/api/payment/status")
def payment_status():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT status, admin_override_status, amount
        FROM payments
        WHERE user_id=?
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],))
    payment = c.fetchone()

    # Also get user's level to return correct expected amount
    c.execute("SELECT level FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    conn.close()

    if not payment:
        return jsonify({"status": "unpaid", "amount": 0})

    override = payment["admin_override_status"]
    status = payment["status"]
    level = user["level"] if user else "300"
    amount = get_amount_for_level(level)

    if override == "paid" or status == "paid":
        display_status = "admin" if override == "paid" else "paid"
    else:
        display_status = "unpaid"

    return jsonify({
        "status": display_status,
        "amount": amount,
        "amount_display": f"₦{amount / 100:,.2f}"
    })
