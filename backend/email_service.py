import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime


def send_email(to_email, subject, body):

    smtp_user = os.environ.get("BREVO_SMTP_USER")
    smtp_password = os.environ.get("BREVO_SMTP_PASSWORD")
    from_email = os.environ.get("EMAIL_FROM", "no-reply@widemindtutorial.com")
    from_name = "Wide Mind Tutorial"

    if not smtp_user or not smtp_password:
        print("BREVO_SMTP_USER or BREVO_SMTP_PASSWORD missing")
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
        print(f"[EMAIL] Attempting to send to {to_email}")
        print(f"[EMAIL] SMTP user: {smtp_user}")
        print(f"[EMAIL] From email: {from_email}")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = to_email
        msg.attach(MIMEText(html_content, "html"))

        print("[EMAIL] Connecting to smtp-relay.brevo.com:587...")
        with smtplib.SMTP("smtp-relay.brevo.com", 587, timeout=20) as server:
            server.set_debuglevel(1)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_password)
            print("[EMAIL] Logged in, sending...")
            server.sendmail(from_email, to_email, msg.as_string())

        print(f"[EMAIL] Successfully sent to {to_email}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        print(f"[EMAIL] Auth failed: {e}")
        return False
    except smtplib.SMTPException as e:
        print(f"[EMAIL] SMTP error: {e}")
        return False
    except Exception as e:
        print(f"[EMAIL] Unexpected error: {type(e).__name__}: {e}")
        return False


# =====================
# WELCOME EMAIL
# =====================
def send_welcome_email(to_email, name):
    first_name = name.split()[0].capitalize()
    body = f"""
    <p style="font-size:18px;font-weight:700;color:#8B7500;">Welcome to Wide Mind Tutorial! 🎉</p>
    <p>Hi <strong>{first_name}</strong>,</p>
    <p>
        We're excited to have you on board. Your account has been created successfully
        and you're one step away from accessing all your course materials.
    </p>
    <p><strong>Here's what you get with full access:</strong></p>
    <ul style="padding-left:20px;line-height:2;">
        <li>📄 Full PDF notes for all your courses</li>
        <li>🎧 Audio lectures you can listen to anywhere</li>
        <li>🔔 Real-time notifications for new materials</li>
    </ul>
    <p>
        To unlock your access, simply log in and complete your payment.
    </p>
    <div style="text-align:center;margin:24px 0;">
        <a href="https://www.widemindtutorial.com"
           style="background:linear-gradient(135deg,#8B7500,#d4af37);color:#fff;
                  padding:14px 32px;border-radius:8px;text-decoration:none;
                  font-weight:bold;font-size:15px;">
            Get Started →
        </a>
    </div>
    <p>If you have any questions, feel free to reach out via our contact page.</p>
    <p>Welcome aboard! 💛<br><strong>Wide Mind Tutorial Team</strong></p>
    """
    return send_email(to_email, "Welcome to Wide Mind Tutorial! 🎉", body)


# =====================
# PAYMENT SUCCESS EMAIL
# =====================
def send_payment_success_email(to_email, name):
    first_name = name.split()[0].capitalize()
    body = f"""
    <p style="font-size:18px;font-weight:700;color:#8B7500;">Payment Confirmed! ✅</p>
    <p>Hi <strong>{first_name}</strong>,</p>
    <p>
        Your payment has been received and your account is now <strong>fully active</strong>.
        You now have complete access to all course materials.
    </p>
    <p><strong>You can now access:</strong></p>
    <ul style="padding-left:20px;line-height:2;">
        <li>📄 PDF notes for all your courses</li>
        <li>🎧 Audio lectures for all sessions</li>
        <li>🔔 Push notifications for new uploads</li>
    </ul>
    <div style="text-align:center;margin:24px 0;">
        <a href="https://www.widemindtutorial.com/account"
           style="background:linear-gradient(135deg,#8B7500,#d4af37);color:#fff;
                  padding:14px 32px;border-radius:8px;text-decoration:none;
                  font-weight:bold;font-size:15px;">
            Go to My Account →
        </a>
    </div>
    <p>Study hard and excel! 💛<br><strong>Wide Mind Tutorial Team</strong></p>
    """
    return send_email(to_email, "Payment Confirmed — Your Access is Active! ✅", body)


# =====================
# NEW MATERIAL EMAIL
# =====================
def send_new_material_email(to_email, name, material_title, course_title, file_type, course_id):
    first_name = name.split()[0].capitalize()
    icon = "📄" if file_type == "pdf" else "🎧"
    type_label = "PDF Notes" if file_type == "pdf" else "Audio Lecture"
    body = f"""
    <p style="font-size:18px;font-weight:700;color:#8B7500;">New Material Available! {icon}</p>
    <p>Hi <strong>{first_name}</strong>,</p>
    <p>
        A new <strong>{type_label}</strong> has just been added to your course materials.
    </p>
    <div style="background:#fff8e1;border:1px solid #e6d8b5;border-radius:10px;
                padding:16px;margin:20px 0;">
        <p style="margin:0;font-size:14px;color:#555;">Course</p>
        <p style="margin:4px 0 12px;font-weight:700;color:#3c2f1f;font-size:16px;">{course_title}</p>
        <p style="margin:0;font-size:14px;color:#555;">Material</p>
        <p style="margin:4px 0 0;font-weight:700;color:#3c2f1f;font-size:16px;">{icon} {material_title}</p>
    </div>
    <div style="text-align:center;margin:24px 0;">
        <a href="https://www.widemindtutorial.com/course/{course_id}"
           style="background:linear-gradient(135deg,#8B7500,#d4af37);color:#fff;
                  padding:14px 32px;border-radius:8px;text-decoration:none;
                  font-weight:bold;font-size:15px;">
            View Material →
        </a>
    </div>
    <p>Keep studying! 💛<br><strong>Wide Mind Tutorial Team</strong></p>
    """
    return send_email(
        to_email,
        f"New {type_label} Available — {course_title} {icon}",
        body
    )

