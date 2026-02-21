import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

def send_email(to_email, subject, message):
    try:
        sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))

        email = Mail(
            from_email=os.environ.get("EMAIL_FROM"),
            to_emails=to_email,
            subject=subject,
            html_content=f"""
                <div style="font-family:Arial;">
                    <h2>{subject}</h2>
                    <p>{message}</p>
                    <hr>
                    <small>WideMind Tutorial</small>
                </div>
            """
        )

        response = sg.send(email)
        return True

    except Exception as e:
        print("Email failed:", e)
        return False