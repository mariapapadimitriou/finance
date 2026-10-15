"""The emails that aren't codes: the welcome email (THL-139 N-04) and the note
that an account was deleted (THL-116 D-05).

Each is (subject, plain text, HTML). The plain text says everything; the HTML
is the same words laid out as the Handoff file draws N-04, with inline styles
only, since mail apps drop stylesheets. Nothing here sends anything: app.py
hands these to `mailer.send`, or prints them when no mail server is set up.
"""

from __future__ import annotations

from html import escape

# N-04's three steps, in order.
WELCOME_STEPS = (
    ("1. Link your accounts", "So Pearl sees your whole picture. Read-only, always."),
    ("2. See your safe to spend", "What you can spend this month without second-guessing."),
    ("3. Follow your path", "Know your money, keep a cushion, grow it. One milestone at a time."),
)
TAGLINE = "Know what’s yours. Keep a cushion. Grow what you’ve got."
# The design leaves the company's legal name as a placeholder until it is
# incorporated; Pearl is what she knows it by.
FOOTER = "You’re getting this because you created a Pearl account. Pearl, Toronto, Ontario"

_INK = "#1c1b2e"
_MUTED = "#5f5d78"
_ROSE = "#b8255a"
_LINE = "#f3dde4"


def welcome(first_name: str | None, link: str) -> tuple[str, str, str]:
    """N-04: sent once, when the account is made."""
    title = f"Welcome to Pearl, {first_name}" if first_name else "Welcome to Pearl"
    intro = "You’ve taken the first step. Here’s what happens next."
    steps_text = "\n\n".join(f"{t}\n{d}" for t, d in WELCOME_STEPS)
    text = (f"{title}\n\n{intro}\n\n{steps_text}\n\nOpen Pearl: {link}\n\n"
            f"{TAGLINE}\n\n{FOOTER}")
    rows = "".join(
        f'<tr><td style="padding:16px 20px;{"border-top:1px solid " + _LINE + ";" if i else ""}">'
        f'<div style="font-size:15px;line-height:22px;color:{_INK};font-weight:500">{escape(t)}</div>'
        f'<div style="font-size:13px;line-height:18px;color:{_MUTED}">{escape(d)}</div></td></tr>'
        for i, (t, d) in enumerate(WELCOME_STEPS))
    html = f"""<!doctype html>
<html lang="en"><body style="margin:0;background:#fbf7f5;font-family:Figtree,Helvetica,Arial,sans-serif;color:{_INK}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:40px 16px">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%">
<tr><td align="center" style="font-family:Georgia,serif;font-size:28px;font-weight:600;padding-bottom:28px">pearl</td></tr>
<tr><td style="font-family:Georgia,serif;font-size:30px;line-height:36px;font-weight:600;padding-bottom:16px">{escape(title)}</td></tr>
<tr><td style="font-size:16px;line-height:24px;color:{_MUTED};padding-bottom:20px">{escape(intro)}</td></tr>
<tr><td><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid {_LINE};border-radius:16px">{rows}</table></td></tr>
<tr><td style="padding:24px 0"><a href="{escape(link, quote=True)}" style="display:block;text-align:center;background:{_ROSE};color:#ffffff;text-decoration:none;font-weight:600;font-size:16px;line-height:56px;border-radius:999px">Open Pearl</a></td></tr>
<tr><td style="font-size:13px;line-height:18px;color:{_MUTED};padding-bottom:16px">{escape(TAGLINE)}</td></tr>
<tr><td style="font-size:13px;line-height:18px;color:{_MUTED}">{escape(FOOTER)}</td></tr>
</table></td></tr></table></body></html>"""
    return title, text, html


def account_deleted(first_name: str | None) -> tuple[str, str]:
    """D-05's "We’ve sent a confirmation": to the address the account had."""
    hello = f"Hi {first_name}," if first_name else "Hi,"
    return ("Your Pearl account is deleted",
            f"{hello}\n\nYour Pearl account is deleted. We’ve disconnected your banks, "
            "signed you out on every device, and deleted your accounts, transactions, "
            "goals and settings. Anything left in our host’s backups is gone within "
            "30 days.\n\nWe keep only a record that your account existed and when it "
            "was deleted.\n\nIf you didn’t do this, reply to this email straight away.")
