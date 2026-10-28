"""Sending e-mail through an ordinary mailbox (SMTP), e.g. Gmail with an app password.

Switched on by SMTP_USER and SMTP_PASSWORD; SMTP_HOST defaults to Gmail,
SMTP_PORT to 465 (SSL), MAIL_FROM to SMTP_USER.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def enabled() -> bool:
    return bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))


def send(to: str, subject: str, text: str) -> None:
    user = os.environ["SMTP_USER"]
    message = EmailMessage()
    message["From"] = os.environ.get("MAIL_FROM") or f"Страховой аналитик <{user}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20) as server:
            server.login(user, os.environ["SMTP_PASSWORD"])
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            server.login(user, os.environ["SMTP_PASSWORD"])
            server.send_message(message)
