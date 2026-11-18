"""Manually send ONE approved EnergyBrew issue to ONE consented test mailbox.

Bulk email and scheduled subscriber delivery are intentionally NOT implemented:
they require opt-in records, unsubscribe handling, and a verified email provider.
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path

from newsletter import EditorialError, render_html, render_text, validate_approved


def address(raw: str) -> str:
    name, email_addr = parseaddr(raw or "")
    if name or not email_addr or "\r" in raw or "\n" in raw:
        raise EditorialError("Test email must be a single plain email address")
    if email_addr != raw.strip() or email_addr.count("@") != 1:
        raise EditorialError("Invalid or multiple recipients")
    return email_addr


def prepare_message(edition: dict, sender: str, recipient: str) -> EmailMessage:
    validate_approved(edition)
    msg = EmailMessage()
    msg["From"] = address(sender)
    msg["To"] = address(recipient)
    msg["Subject"] = "EnergyBrew — Your 5-minute energy brief — " + edition["edition_date"]
    msg.set_content(render_text(edition))
    msg.add_alternative(render_html(edition), subtype="html")
    return msg


def deliver_test(edition: dict, *, env: dict[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    # An explicit second approval is needed to send anything outside the repo.
    if env.get("NEWSLETTER_ALLOW_TEST_SEND") != "YES":
        raise EditorialError("NEWSLETTER_ALLOW_TEST_SEND=YES required for test delivery")
    required = ("NEWSLETTER_TEST_TO", "NEWSLETTER_FROM", "SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD")
    absent = [name for name in required if not env.get(name)]
    if absent:
        raise EditorialError("Missing protected email configuration: " + ", ".join(absent))
    port = int(env.get("SMTP_PORT", "587"))
    if port not in (465, 587):
        raise EditorialError("Only TLS-enabled SMTP ports 465 and 587 are permitted")
    message = prepare_message(edition, env["NEWSLETTER_FROM"], env["NEWSLETTER_TEST_TO"])
    host = env["SMTP_HOST"]
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context()) as server:
            server.login(env["SMTP_USERNAME"], env["SMTP_PASSWORD"])
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(env["SMTP_USERNAME"], env["SMTP_PASSWORD"])
            server.send_message(message)
    return "Sent ONE test email to configured test mailbox. Not a subscriber broadcast."


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--edition", type=Path, required=True)
    parser.add_argument("--send-test", action="store_true",
                        help="Requires encrypted SMTP secrets and explicit NEWSLETTER_ALLOW_TEST_SEND=YES")
    args = parser.parse_args()
    edition = json.loads(args.edition.read_text(encoding="utf-8"))
    validate_approved(edition)
    if args.send_test:
        print(deliver_test(edition))
    else:
        print("Approval metadata valid. Dry run only: NO EMAIL SENT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
