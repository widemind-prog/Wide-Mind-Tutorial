print("EMAIL SERVICE LOADED")
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from datetime import datetime


def send_email(to_email, subject, body):

    api_key = os.environ.get("SENDGRID_API_KEY")
    from_email = os.environ.get("EMAIL_FROM", "no-reply@widemindtutorial.com")

    if not api_key:
        print("SENDGRID_API_KEY missing")
        return False

    try:
        sg = SendGridAPIClient(api_key)

        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject,
            html_content=f"""
<div style="margin:0;padding:0;background-color:#fdf6e3;">

  <div style="max-width:600px;margin:0 auto;
              background-color:#ffffff;
              font-family:'Poppins', Arial, sans-serif;
              border-radius:14px;
              overflow:hidden;
              border:1px solid #e6d8b5;">

    <!-- HEADER -->
    <div style="background:linear-gradient(135deg,#8B7500,#d4af37);
                padding:25px;
                text-align:center;">

      <img src="https://www.widemindtutorial.com/static/images/logo.png"
           alt="Wide Mind Tutorial"
           style="max-width:130px;margin-bottom:12px;">

      <h2 style="color:#f0e6d2;
                 margin:0;
                 font-size:22px;
                 letter-spacing:1px;">
        Wide Mind Tutorial
      </h2>

    </div>

    <!-- BODY -->
    <div style="padding:32px;
                color:#3c2f1f;
                font-size:15px;
                line-height:1.7;">

      <div style="background-color:#fffaf0;
                  padding:20px;
                  border-radius:10px;
                  border:1px solid #f0e6d2;">

        {body}

      </div>

      <p style="margin-top:28px;
                font-size:12px;
                color:#8B7500;">
        Sent on {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
      </p>

      <hr style="margin:25px 0;
                 border:none;
                 border-top:1px solid #e6d8b5;">

      <p style="font-size:13px;
                color:#555;
                margin:0;">
        This is an official email from
        <strong>Wide Mind Tutorial</strong>.
      </p>

      <p style="font-size:12px;
                color:#777;
                margin-top:8px;">
        Please do not reply to this message.
        For support, visit our website.
      </p>

    </div>

    <!-- FOOTER -->
    <div style="background-color:#8B7500;
                padding:18px;
                text-align:center;
                font-size:12px;
                color:#f0e6d2;">

      © {datetime.utcnow().year} Wide Mind Tutorial<br>
      www.widemindtutorial.com

    </div>

  </div>
</div>
"""
        )

        response = sg.send(message)

        print("SendGrid status:", response.status_code)

        return response.status_code in (200, 202)

    except Exception as e:
        print("Email failed:", e)
        return False