from flask import Blueprint, jsonify, session, redirect, request
import requests
import os
from backend.db import get_db, is_admin
from backend.email_service import send_payment_success_email

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

    amount = int(20413.06 * 100)

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
        "callback_url": "https://www.widemindtutorial.com/payment/callback"
    }

    try:
        resp = requests.post(
            "https://api.paystack.co/transaction/initialize",
            json=payload,
            headers=headers,
            timeout=10
        )
        resp.raise_for_status()
        resp_json = resp.json()
    except requests.RequestException:
        return jsonify({"status": False, "message": "Failed to initialize payment"}), 500

    if resp_json.get("status"):
        return jsonify({"status": True, "data": resp_json["data"]})

    return jsonify({"status": False, "message": "Payment initialization failed"}), 500


# ------------------------------------
# PAYSTACK CALLBACK (REDIRECT FLOW)
# ------------------------------------
@payment_bp.route("/payment/callback", methods=["GET"])
def payment_callback():
    reference = request.args.get("reference")
    if not reference:
        return redirect("/account?payment=failed")

    headers = {"Authorization": f"Bearer {os.environ.get('PAYSTACK_SECRET_KEY')}"}

    try:
        resp = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers=headers,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return redirect("/account?payment=failed")

    if not (data.get("status") and data["data"]["status"] == "success"):
        return redirect("/account?payment=failed")

    email = data["data"]["customer"]["email"]
    amount = data["data"]["amount"]

    if amount != 2041306:
        return redirect("/account?payment=invalid_amount")

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id, name FROM users WHERE email=?", (email,))
    user = c.fetchone()
    if not user:
        conn.close()
        return redirect("/account?payment=user_not_found")

    user_id = user["id"]
    user_name = user["name"]

    c.execute("""
        SELECT * FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 1
    """, (user_id,))
    payment = c.fetchone()

    already_paid = False

    if not payment:
        c.execute("""
            INSERT INTO payments (user_id, amount, status, reference, paid_at)
            VALUES (?, ?, 'paid', ?, datetime('now'))
        """, (user_id, amount, reference))

    elif payment.get("admin_override_status") == "unpaid":
        conn.close()
        return redirect("/account?payment=blocked")

    elif payment.get("admin_override_status") == "paid":
        already_paid = True

    elif payment["status"] == "unpaid":
        c.execute("""
            UPDATE payments SET status='paid', reference=?, paid_at=datetime('now') WHERE id=?
        """, (reference, payment["id"]))
    else:
        already_paid = True

    conn.commit()
    conn.close()

    # Send payment success email
    if not already_paid:
        try:
            send_payment_success_email(email, user_name)
        except Exception as e:
            print("Payment email failed:", e)

    return redirect("/account?payment=success")


# ------------------------------------
# PAYMENT STATUS
# ------------------------------------
@payment_bp.route("/api/payment/status", methods=["GET"])
def payment_status():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    user_id = session["user_id"]

    if is_admin(user_id):
        return jsonify({
            "status": "admin", "amount": 0, "reference": None, "paid_at": None
        }), 200

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT * FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 1
    """, (user_id,))
    payment = c.fetchone()

    payment_data = dict(payment) if payment else {
        "id": None, "user_id": user_id, "amount": 2041306,
        "status": "unpaid", "reference": None,
        "paid_at": None, "admin_override_status": None
    }

    if payment_data.get("admin_override_status") in ("paid", "unpaid"):
        payment_data["status"] = payment_data["admin_override_status"]
        conn.close()
        return jsonify(payment_data), 200

    if payment_data.get("reference") and payment_data["status"] == "unpaid":
        headers = {"Authorization": f"Bearer {os.environ.get('PAYSTACK_SECRET_KEY')}"}
        try:
            resp = requests.get(
                f"https://api.paystack.co/transaction/verify/{payment_data['reference']}",
                headers=headers, timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") and data["data"]["status"] == "success":
                c.execute("""
                    UPDATE payments SET status='paid', paid_at=datetime('now') WHERE id=?
                """, (payment_data["id"],))
                conn.commit()
                payment_data["status"] = "paid"
                payment_data["paid_at"] = data["data"].get("paid_at")
        except requests.RequestException:
            pass

    conn.close()
    return jsonify(payment_data), 200
