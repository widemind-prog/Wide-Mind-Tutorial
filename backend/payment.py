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

RERUN_AMOUNTS = {
    "300": 359231,
    "400": 536565,
}

def get_amount_for_level(level):
    return LEVEL_AMOUNTS.get(str(level), 1026375)

def get_rerun_amount(rerun_level):
    return RERUN_AMOUNTS.get(str(rerun_level), 359231)

# =====================
# MAIN PAYMENT INIT
# =====================
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

    amount = get_amount_for_level(user["level"])

    # Sync amount in case of migration
    c.execute("""
        UPDATE payments SET amount=?
        WHERE user_id=? AND status != 'paid'
        AND (admin_override_status IS NULL OR admin_override_status != 'paid')
    """, (amount, session["user_id"]))
    conn.commit()
    conn.close()

    secret_key = current_app.config["PAYSTACK_SECRET_KEY"]
    headers = {"Authorization": f"Bearer {secret_key}", "Content-Type": "application/json"}
    payload = {
        "email": user["email"],
        "amount": amount,
        "callback_url": "https://www.widemindtutorial.com/api/payment/callback",
        "metadata": {"payment_type": "main"}
    }

    response = req.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    return jsonify(response.json())

# =====================
# RERUN PAYMENT INIT
# =====================
@payment_bp.route("/api/payment/rerun/init", methods=["POST"])
def init_rerun_payment():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.get_json() or {}
    rerun_level = str(data.get("rerun_level", ""))

    if rerun_level not in ("300", "400"):
        return jsonify({"error": "Invalid rerun level"}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT email, level, semester FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "User not found"}), 404

    # Must have paid main fee
    c.execute("""
        SELECT status, admin_override_status FROM payments
        WHERE user_id=? ORDER BY id DESC LIMIT 1
    """, (session["user_id"],))
    main_payment = c.fetchone()
    if not main_payment or (
        main_payment["status"] != "paid" and
        main_payment["admin_override_status"] != "paid"
    ):
        conn.close()
        return jsonify({"error": "You must pay your main fee before purchasing a rerun pass"}), 403

    # Rerun level must be below user's level
    user_level = int(user["level"])
    if int(rerun_level) >= user_level:
        conn.close()
        return jsonify({"error": "Rerun level must be below your current level"}), 400

    # Check not already paid for this rerun level
    c.execute("""
        SELECT status, admin_override_status FROM rerun_passes
        WHERE user_id=? AND rerun_level=?
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"], rerun_level))
    existing = c.fetchone()
    if existing and (
        existing["status"] == "paid" or
        existing["admin_override_status"] == "paid"
    ):
        conn.close()
        return jsonify({"error": f"You already have a {rerun_level}L rerun pass"}), 400

    amount = get_rerun_amount(rerun_level)

    # Create or update pending rerun pass record
    if existing:
        c.execute("""
            UPDATE rerun_passes SET amount=?, status='unpaid', reference=NULL
            WHERE user_id=? AND rerun_level=?
        """, (amount, session["user_id"], rerun_level))
    else:
        c.execute("""
            INSERT INTO rerun_passes (user_id, rerun_level, amount, status)
            VALUES (?, ?, ?, 'unpaid')
        """, (session["user_id"], rerun_level, amount))
    conn.commit()
    conn.close()

    secret_key = current_app.config["PAYSTACK_SECRET_KEY"]
    headers = {"Authorization": f"Bearer {secret_key}", "Content-Type": "application/json"}
    payload = {
        "email": user["email"],
        "amount": amount,
        "callback_url": "https://www.widemindtutorial.com/api/payment/rerun/callback",
        "metadata": {
            "payment_type": "rerun",
            "rerun_level": rerun_level,
            "user_id": session["user_id"]
        }
    }

    response = req.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    return jsonify(response.json())

# =====================
# MAIN PAYMENT CALLBACK
# =====================
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
            expected = get_amount_for_level(user["level"])
            if amount_paid >= expected:
                c.execute("""
                    UPDATE payments SET status='paid', reference=?, paid_at=datetime('now')
                    WHERE user_id=?
                """, (reference, user["id"]))
                conn.commit()
        conn.close()

    return redirect("/account?payment=callback")

# =====================
# RERUN PAYMENT CALLBACK
# =====================
@payment_bp.route("/api/payment/rerun/callback")
def rerun_payment_callback():
    reference = request.args.get("reference")
    if not reference:
        return redirect("/account?payment=failed")

    secret_key = current_app.config.get("PAYSTACK_SECRET_KEY")
    headers = {"Authorization": f"Bearer {secret_key}"}
    response = req.get(f"https://api.paystack.co/transaction/verify/{reference}", headers=headers)
    data = response.json()

    if data.get("data", {}).get("status") == "success":
        meta = data["data"].get("metadata", {})
        rerun_level = str(meta.get("rerun_level", ""))
        customer_email = data["data"]["customer"]["email"]
        amount_paid = data["data"]["amount"]

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE email=?", (customer_email,))
        user = c.fetchone()
        if user and rerun_level in ("300", "400"):
            expected = get_rerun_amount(rerun_level)
            if amount_paid >= expected:
                c.execute("""
                    UPDATE rerun_passes
                    SET status='paid', reference=?, paid_at=datetime('now')
                    WHERE user_id=? AND rerun_level=?
                """, (reference, user["id"], rerun_level))
                conn.commit()
        conn.close()

    return redirect("/account?payment=rerun_callback")

# =====================
# MAIN PAYMENT STATUS
# =====================
@payment_bp.route("/api/payment/status")
def payment_status():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT status, admin_override_status, amount FROM payments
        WHERE user_id=? ORDER BY id DESC LIMIT 1
    """, (session["user_id"],))
    payment = c.fetchone()

    c.execute("SELECT level FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    conn.close()

    level = user["level"] if user else "300"
    amount = get_amount_for_level(level)

    if not payment:
        return jsonify({"status": "unpaid", "amount": amount, "amount_display": f"₦{amount/100:,.2f}"})

    override = payment["admin_override_status"]
    status = payment["status"]
    if override == "paid" or status == "paid":
        display_status = "paid"
    else:
        display_status = "unpaid"

    return jsonify({
        "status": display_status,
        "amount": amount,
        "amount_display": f"₦{amount/100:,.2f}"
    })

# =====================
# RERUN PASSES STATUS
# =====================
@payment_bp.route("/api/payment/rerun/status")
def rerun_status():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT level, semester FROM users WHERE id=?", (session["user_id"],))
    user = c.fetchone()
    if not user:
        conn.close()
        return jsonify({"passes": [], "eligible_levels": []})

    user_level = int(user["level"])

    # Eligible rerun levels = all levels below user's level that have courses this semester
    eligible = []
    for lvl in ["300", "400"]:
        if int(lvl) < user_level:
            # Check if there are any courses for this level + current semester
            c.execute("""
                SELECT COUNT(*) AS cnt FROM courses
                WHERE level=? AND semester=?
            """, (lvl, user["semester"]))
            row = c.fetchone()
            if row and row["cnt"] > 0:
                eligible.append(lvl)

    # Get existing rerun passes
    c.execute("""
        SELECT rerun_level, status, admin_override_status, amount
        FROM rerun_passes WHERE user_id=?
    """, (session["user_id"],))
    passes_raw = c.fetchall()
    conn.close()

    passes = {}
    for p in passes_raw:
        effective = p["admin_override_status"] if p["admin_override_status"] else p["status"]
        passes[p["rerun_level"]] = {
            "status": effective,
            "amount": p["amount"],
            "amount_display": f"₦{p['amount']/100:,.2f}"
        }

    result = []
    for lvl in eligible:
        amount = get_rerun_amount(lvl)
        existing = passes.get(lvl)
        result.append({
            "rerun_level": lvl,
            "status": existing["status"] if existing else "unpaid",
            "amount": amount,
            "amount_display": f"₦{amount/100:,.2f}"
        })

    return jsonify({"passes": result, "eligible_levels": eligible})
