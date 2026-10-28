"""Injectable SMTP reset delivery. Secrets are not returned by the API or logged."""

import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote

from fastapi import BackgroundTasks, HTTPException

from app.core.config import get_settings
from app.core.logging import get_logger


class PasswordResetMailer:
    def send(self, email: str, reset_token: str) -> None:
        settings = get_settings()
        message = EmailMessage()
        message["From"] = settings.smtp_from_email
        message["To"] = email
        message["Subject"] = "Reset your ChangeGuard password"
        # Fragment keeps the token out of server-side URL/query logs.
        link = f"{settings.frontend_url.rstrip('/')}/reset-password#token={quote(reset_token, safe='')}"
        message.set_content(
            f"Use this single-use link to reset your password:\n{link}\n\nIf you did not request this, ignore this email."
        )
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                if settings.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password or "")
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            # SMTP exceptions can include addresses/credentials/server transcripts.
            get_logger(__name__).error("password_reset_delivery_failed")

    def queue(self, tasks: BackgroundTasks, email: str, reset_token: str) -> None:
        tasks.add_task(self.send, email, reset_token)


def get_password_reset_mailer() -> PasswordResetMailer:
    if not get_settings().smtp_host:
        # Fail identically before looking up an account.
        raise HTTPException(status_code=503, detail="Password reset is temporarily unavailable")
    return PasswordResetMailer()
