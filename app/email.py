import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .config import settings
import logging

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, html_content: str, text_content:str=""):
    """Send email using SMTP"""
    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        message["To"] = to_email

        # Attach plain text first
        text_part = MIMEText(text_content, "plain")
        html_part = MIMEText(html_content, "html")

        message.attach(text_part)
        message.attach(html_part)

        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=20
        ) as server:

            server.set_debuglevel(1)

            server.ehlo()
            server.starttls()
            server.ehlo()

            server.login(
                settings.smtp_username,
                settings.smtp_password
            )

            server.send_message(message)

        logger.info(f"Email sent successfully to {to_email}")
        return True

    except Exception as e:
        logger.error(f"SMTP ERROR: {str(e)}")
        return False


def send_password_reset_email(email: str, reset_token: str):
    """Send password reset email with token"""

    reset_link = (
        f"{settings.frontend_url}/reset-password?token={reset_token}"
    )

    # Plain text version (helps avoid spam)
    text_content = f"""
Password Reset Request

We received a request to reset your Expense Tracker password.

Reset your password here:
{reset_link}

This link expires in 30 minutes.

If you did not request this, you can safely ignore this email.

Regards,
{settings.smtp_from_name} Team
"""

    # HTML version
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                background-color: #f9fafb;
                margin: 0;
                padding: 20px;
            }}

            .container {{
                max-width: 600px;
                margin: 0 auto;
            }}

            .content {{
                background-color: white;
                padding: 30px;
                border-radius: 10px;
                border: 1px solid #e5e7eb;
            }}

            .button {{
                display: inline-block;
                padding: 12px 24px;
                background-color: #4F46E5;
                color: white !important;
                text-decoration: none;
                border-radius: 6px;
                font-weight: bold;
            }}

            .footer {{
                margin-top: 25px;
                font-size: 12px;
                color: #666;
                text-align: center;
            }}

            .link {{
                word-break: break-all;
                color: #4F46E5;
                font-size: 13px;
            }}
        </style>
    </head>

    <body>
        <div class="container">
            <div class="content">

                <h2 style="color:#4F46E5;">
                    Reset Your Password
                </h2>

                <p>Hello,</p>

                <p>
                    We received a request to reset the password
                    for your Expense Tracker account.
                </p>

                <p>
                    Click the button below to create a new password:
                </p>

                <p style="text-align:center;">
                    <a href="{reset_link}" class="button">
                        Reset Password
                    </a>
                </p>

                <p>
                    Or copy this link into your browser:
                </p>

                <p class="link">
                    {reset_link}
                </p>

                <p>
                    <strong>
                        This link expires in 30 minutes.
                    </strong>
                </p>

                <p>
                    If you did not request this reset,
                    simply ignore this email.
                </p>

            </div>

            <div class="footer">
                Best regards,<br>
                {settings.smtp_from_name} Team
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(
        email,
        "Reset your Expense Tracker password",
        html_content,
        text_content
    )