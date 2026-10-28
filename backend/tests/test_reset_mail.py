"""SMTP adapter behavior without opening network connections."""

from app.core.config import get_settings
from app.core.reset_mail import PasswordResetMailer


def test_mailer_uses_verified_tls_and_fragment_link(monkeypatch):
    calls = {}

    class SMTP:
        def __init__(self, host, port, timeout):
            calls["connection"] = (host, port, timeout)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, context):
            calls["verify_mode"] = context.verify_mode
            calls["check_hostname"] = context.check_hostname

        def login(self, username, password):
            calls["auth"] = (username, password)

        def send_message(self, message):
            calls["message"] = message

    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_username", "mailer")
    monkeypatch.setattr(settings, "smtp_password", "smtp-secret")
    monkeypatch.setattr(settings, "smtp_starttls", True)
    monkeypatch.setattr("app.core.reset_mail.smtplib.SMTP", SMTP)
    PasswordResetMailer().send("owner@example.com", "signed-reset-token")
    assert calls["check_hostname"] is True
    assert calls["auth"] == ("mailer", "smtp-secret")
    assert calls["message"]["To"] == "owner@example.com"
    body = calls["message"].get_content()
    assert "/reset-password#token=signed-reset-token" in body
    assert "?token=" not in body


def test_mail_failures_do_not_log_exception_or_token(monkeypatch, caplog):
    def fail(*args, **kwargs):
        raise OSError("smtp-password-and-private-message")

    monkeypatch.setattr("app.core.reset_mail.smtplib.SMTP", fail)
    PasswordResetMailer().send("owner@example.com", "private-reset-token")
    output = " ".join(str(record.msg) for record in caplog.records)
    assert "password_reset_delivery_failed" in output
    assert "smtp-password-and-private-message" not in output
    assert "private-reset-token" not in output
