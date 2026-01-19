from flask import Blueprint, jsonify, session
import requests
import os
from backend.db import get_db

payment_bp = Blueprint("payment_bp", __name__)

@payment_bp.route("/api/payment/init", methods=["POST"])
def init_payment():
    """
    Initialize Paystack payment for the logged-in user.
    Full-page redirect is used instead of modal.
    """
    if "user_id" not in session:
        return jsonify({"status": False, "message": "Not authenticated"}), 401

    user_id = session["user_id"]
    amount = 20000 * 100  # Paystack expects amount in kobo (₦20,000)

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
        # Redirect to account page with query string for toast
        "callback_url": "https://wide-mind-tutorial-gptu.onrender.com/account?payment=callback"
    }

    try:
        resp = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
        resp.raise_for_status()
        resp_json = resp.json()
    except requests.RequestException as e:
        return jsonify({"status": False, "message": "Failed to initialize payment"}), 500

    if resp_json.get("status"):
        return jsonify({"status": True, "data": resp_json["data"]})
    else:
        return jsonify({"status": False, "message": resp_json.get("message", "Failed to initialize payment")})
