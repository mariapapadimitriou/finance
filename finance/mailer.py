"""Sending the one email the app sends: a link to reset a forgotten password.

Plain SMTP, so any free mailbox can send it. The setup this was built for is
a Gmail account with an app password (free, around 500 messages a day); the
host and port default to Gmail's, and any other SMTP server works by setting
them.

    SPENDIE_SMTP_USER      the address that signs in to send (e.g. a Gmail)
    SPENDIE_SMTP_PASSWORD  its app password
    SPENDIE_SMTP_HOST      default smtp.gmail.com
    SPENDIE_SMTP_PORT      default 587 (STARTTLS)
    SPENDIE_MAIL_FROM      default the SMTP user, e.g. "Spendie <you@gmail.com>"

Until the user and password are set, `configured()` is false and "Forgot
password?" says email isn't set up rather than pretending to send.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

USER_ENV = "SPENDIE_SMTP_USER"
PASSWORD_ENV = "SPENDIE_SMTP_PASSWORD"
HOST_ENV = "SPENDIE_SMTP_HOST"
PORT_ENV = "SPENDIE_SMTP_PORT"
FROM_ENV = "SPENDIE_MAIL_FROM"


def configured() -> bool:
    return bool(os.environ.get(USER_ENV, "").strip()
                and os.environ.get(PASSWORD_ENV, "").strip())


def send(to: str, subject: str, text: str) -> None:
    """Send one plain-text message. Raises if the server refuses it."""
    user = os.environ.get(USER_ENV, "").strip()
    password = os.environ.get(PASSWORD_ENV, "").replace(" ", "").strip()
    host = os.environ.get(HOST_ENV, "").strip() or "smtp.gmail.com"
    port = int(os.environ.get(PORT_ENV, "").strip() or 587)

    msg = EmailMessage()
    msg["From"] = os.environ.get(FROM_ENV, "").strip() or f"Spendie <{user}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)

    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as s:
            s.login(user, password)
            s.send_message(msg)
        return
    with smtplib.SMTP(host, port, timeout=15) as s:
        s.ehlo()
        if s.has_extn("starttls"):
            s.starttls(context=context)
            s.ehlo()
        if user and password and s.has_extn("auth"):
            s.login(user, password)
        s.send_message(msg)


def mask(email: str) -> str:
    """m•••@outlook.com — enough to recognise, not enough to harvest."""
    local, _, domain = (email or "").partition("@")
    if not domain:
        return "your email"
    return f"{local[:1]}•••@{domain}"
