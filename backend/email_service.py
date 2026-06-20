import os
import requests
from datetime import datetime


def send_email(to_email, subject, body):
    api_key = os.environ.get("BREVO_API_KEY")
    from_email = os.environ.get("EMAIL_FROM", "no-reply@widemindtutorial.com")
    from_name = "Wide Mind Tutorial"

    if not api_key:
        print("[EMAIL] BREVO_API_KEY missing")
        return False

    html_content = f"""
<div style="margin:0;padding:0;background-color:#fdf6e3;">
  <div style="max-width:600px;margin:0 auto;background-color:#ffffff;
              font-family:'Poppins', Arial, sans-serif;border-radius:14px;
              overflow:hidden;border:1px solid #e6d8b5;">
    <div style="background:linear-gradient(135deg,#8B7500,#d4af37);padding:25px;text-align:center;">
      <img src="https://www.widemindtutorial.com/static/images/logo.png"
           alt="Wide Mind Tutorial" style="max-width:130px;margin-bottom:12px;">
    </div>
    <div style="padding:32px;color:#3c2f1f;font-size:15px;line-height:1.7;">
      <div style="background-color:#fffaf0;padding:20px;border-radius:10px;border:1px solid #f0e6d2;">
        {body}
      </div>
      <p style="margin-top:28px;font-size:12px;color:#8B7500;">
        Sent on {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
      </p>
      <hr style="margin:25px 0;border:none;border-top:1px solid #e6d8b5;">
      <p style="font-size:13px;color:#555;margin:0;">
        This is an official email from <strong>Wide Mind Tutorial</strong>.
      </p>
      <p style="font-size:12px;color:#777;margin-top:8px;">
        Please do not reply to this message. For support, visit our website.
      </p>
    </div>
    <div style="background-color:#8B7500;padding:18px;text-align:center;
                font-size:12px;color:#f0e6d2;">
      &copy; {datetime.utcnow().year} Wide Mind Tutorial<br>
      www.widemindtutorial.com
    </div>
  </div>
</div>
"""
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json"
            },
            json={
                "sender": {"name": from_name, "email": from_email},
                "to": [{"email": to_email}],
                "subject": subject,
                "htmlContent": html_content
            },
            timeout=15
        )
        print(f"[EMAIL] Brevo status: {response.status_code} to {to_email}")
        if response.status_code not in (200, 201):
            print(f"[EMAIL] Brevo error: {response.text}")
            return False
        return True
    except Exception as e:
        print(f"[EMAIL] Failed: {type(e).__name__}: {e}")
        return False


# =====================
# OTP EMAIL
# =====================
def send_otp_email(to_email, name, otp):
    first_name = name.split()[0].capitalize()
    body = f"""
    <p style="font-size:18px;font-weight:700;color:#8B7500;">Verify Your Email Address</p>
    <p>Hi <strong>{first_name}</strong>,</p>
    <p>Enter the code below to verify your email and start your <strong>24-hour free trial</strong>.</p>
    <div style="text-align:center;margin:28px 0;">
        <div style="display:inline-block;background:linear-gradient(135deg,#8B7500,#d4af37);
                    color:#fff;font-size:36px;font-weight:800;letter-spacing:12px;
                    padding:18px 32px;border-radius:12px;">
            {otp}
        </div>
    </div>
    <p style="text-align:center;font-size:13px;color:#777;">
        This code expires in <strong>10 minutes</strong>.
    </p>
    <p style="font-size:13px;color:#aaa;">
        If you did not create an account on Wide Mind Tutorial, you can safely ignore this email.
    </p>
    """
    return send_email(to_email, "Your Wide Mind Tutorial Verification Code", body)


# =====================
# WELCOME EMAIL
# =====================
def send_welcome_email(to_email, name):
    first_name = name.split()[0].capitalize()
    body = f"""
    <p style="font-size:18px;font-weight:700;color:#8B7500;">Welcome to Wide Mind Tutorial!</p>
    <p>Hi <strong>{first_name}</strong>,</p>
    <p>
        Your account has been created. Check your email for a verification code to activate
        your <strong>24-hour free trial</strong>.
    </p>
    <p><strong>With full access you get:</strong></p>
    <ul style="padding-left:20px;line-height:2;">
        <li>Full PDF notes for all your courses</li>
        <li>Audio lectures you can listen to anywhere</li>
        <li>Real-time notifications for new materials</li>
    </ul>
    <div style="text-align:center;margin:24px 0;">
        <a href="https://www.widemindtutorial.com/verify-email"
           style="background:linear-gradient(135deg,#8B7500,#d4af37);color:#fff;
                  padding:14px 32px;border-radius:8px;text-decoration:none;
                  font-weight:bold;font-size:15px;">
            Verify My Email
        </a>
    </div>
    <p>Welcome aboard!<br><strong>Wide Mind Tutorial Team</strong></p>
    """
    return send_email(to_email, "Welcome to Wide Mind Tutorial — Verify Your Email", body)


# =====================
# PAYMENT SUCCESS EMAIL
# =====================
def send_payment_success_email(to_email, name):
    first_name = name.split()[0].capitalize()
    body = f"""
    <p style="font-size:18px;font-weight:700;color:#8B7500;">Payment Confirmed!</p>
    <p>Hi <strong>{first_name}</strong>,</p>
    <p>Your payment has been received and your account is now <strong>fully active</strong>.</p>
    <p><strong>You can now access:</strong></p>
    <ul style="padding-left:20px;line-height:2;">
        <li>PDF notes for all your courses</li>
        <li>Audio lectures for all sessions</li>
        <li>Push notifications for new uploads</li>
    </ul>
    <div style="text-align:center;margin:24px 0;">
        <a href="https://www.widemindtutorial.com/account"
           style="background:linear-gradient(135deg,#8B7500,#d4af37);color:#fff;
                  padding:14px 32px;border-radius:8px;text-decoration:none;
                  font-weight:bold;font-size:15px;">
            Go to My Account
        </a>
    </div>
    <p>Study hard and excel!<br><strong>Wide Mind Tutorial Team</strong></p>
    """
    return send_email(to_email, "Payment Confirmed — Your Access is Active!", body)


# =====================
# NEW MATERIAL EMAIL
# =====================
def send_new_material_email(to_email, name, material_title, course_title, file_type, course_id):
    first_name = name.split()[0].capitalize()
    type_label = "PDF Notes" if file_type == "pdf" else "Audio Lecture"
    body = f"""
    <p style="font-size:18px;font-weight:700;color:#8B7500;">New Material Available!</p>
    <p>Hi <strong>{first_name}</strong>,</p>
    <p>A new <strong>{type_label}</strong> has just been added to your course materials.</p>
    <div style="background:#fff8e1;border:1px solid #e6d8b5;border-radius:10px;
                padding:16px;margin:20px 0;">
        <p style="margin:0;font-size:14px;color:#555;">Course</p>
        <p style="margin:4px 0 12px;font-weight:700;color:#3c2f1f;font-size:16px;">{course_title}</p>
        <p style="margin:0;font-size:14px;color:#555;">Material</p>
        <p style="margin:4px 0 0;font-weight:700;color:#3c2f1f;font-size:16px;">{material_title}</p>
    </div>
    <div style="text-align:center;margin:24px 0;">
        <a href="https://www.widemindtutorial.com/course/{course_id}"
           style="background:linear-gradient(135deg,#8B7500,#d4af37);color:#fff;
                  padding:14px 32px;border-radius:8px;text-decoration:none;
                  font-weight:bold;font-size:15px;">
            View Material
        </a>
    </div>
    <p>Keep studying!<br><strong>Wide Mind Tutorial Team</strong></p>
    """
    return send_email(to_email, f"New {type_label} Available — {course_title}", body)
