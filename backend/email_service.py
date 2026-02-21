print("EMAIL SERVICE LOADED")
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


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
            <div style="font-family: Arial; padding: 20px;">
                <p>{body}</p>
                <hr>
                <small>Wide Mind Tutorials</small>
            </div>
            """
        )

        response = sg.send(message)

        print("SendGrid status:", response.status_code)

        return response.status_code in (200, 202)

    except Exception as e:
        print("Email failed:", e)
        return False