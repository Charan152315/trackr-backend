import resend
import logging
from .config import settings

logger = logging.getLogger(__name__)

resend.api_key = settings.resend_api_key


def send_email(to_email: str, subject: str, html_content: str, text_content: str = ""):
    try:
        params = {
            "from": f"{settings.smtp_from_name} <onboarding@resend.dev>",
            "to": [to_email],
            "subject": subject,
            "html": html_content,
        }
        if text_content:
            params["text"] = text_content

        response = resend.Emails.send(params)
        logger.info(f"Email sent via Resend to {to_email}: {response}")
        return True
    except Exception as e:
        logger.error(f"Resend error: {str(e)}")
        return False


def send_password_reset_email(email: str, reset_token: str):
    reset_link = f"{settings.frontend_url}/reset-password?token={reset_token}"

    html_content = f"""
    <div style="font-family:Arial;padding:24px;max-width:520px;margin:0 auto">
        <div style="background:#0c1a2e;padding:20px;border-radius:12px;text-align:center;margin-bottom:24px">
            <h1 style="color:#38bdf8;margin:0;font-size:24px">Trackr</h1>
        </div>
        <h2 style="color:#0f172a;font-size:20px">Reset your password</h2>
        <p style="color:#475569;line-height:1.6">
            We received a request to reset the password for your Trackr account.
            Click the button below to create a new password.
        </p>
        <div style="text-align:center;margin:28px 0">
            <a href="{reset_link}"
               style="background:#38bdf8;color:#0c1a2e;padding:13px 28px;
                      border-radius:8px;text-decoration:none;font-weight:700;
                      font-size:15px;display:inline-block">
                Reset Password
            </a>
        </div>
        <p style="color:#94a3b8;font-size:13px">
            Or copy this link: <a href="{reset_link}" style="color:#38bdf8">{reset_link}</a>
        </p>
        <p style="color:#94a3b8;font-size:13px">
            This link expires in <strong>30 minutes</strong>.
            If you didn't request this, ignore this email.
        </p>
        <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0">
        <p style="color:#cbd5e1;font-size:12px;text-align:center">
            — {settings.smtp_from_name} Team
        </p>
    </div>
    """

    return send_email(email, "Reset your Trackr password", html_content)