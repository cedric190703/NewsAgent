"""Send newsletters via Resend API or SMTP to the mailing list."""

from __future__ import annotations

import asyncio
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from app.core.config import settings
from app.graph.state import Newsletter
from app.services.exporter import to_html, to_markdown
from app.services.store import get_subscriber_emails, get_subscriber_emails_by_groups, get_run

RESEND_API_URL = "https://api.resend.com/emails"


async def _send_via_resend(
    emails: list[str],
    subject: str,
    html_body: str,
    text_body: str,
) -> tuple[int, int, list[str]]:
    """Send emails via Resend HTTP API. Returns (sent, failed, errors)."""
    sent = 0
    failed = 0
    errors: list[str] = []

    from_email = settings.smtp_from_email or "onboarding@resend.dev"
    from_header = f"{settings.smtp_from_name} <{from_email}>"

    async with httpx.AsyncClient(timeout=30) as client:
        for email in emails:
            try:
                resp = await client.post(
                    RESEND_API_URL,
                    headers={
                        "Authorization": f"Bearer {settings.resend_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": from_header,
                        "to": [email],
                        "subject": subject,
                        "html": html_body,
                        "text": text_body,
                    },
                )
                if resp.status_code in (200, 201):
                    sent += 1
                else:
                    failed += 1
                    errors.append(f"{email}: {resp.status_code} {resp.text[:200]}")
            except Exception as exc:
                failed += 1
                errors.append(f"{email}: {exc}")

    return sent, failed, errors


async def _send_via_smtp(
    emails: list[str],
    subject: str,
    html_body: str,
    text_body: str,
) -> tuple[int, int, list[str]]:
    """Send emails via SMTP. Returns (sent, failed, errors)."""
    sent = 0
    failed = 0
    errors: list[str] = []

    try:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)

        for email in emails:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
            msg["To"] = email
            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))
            try:
                server.sendmail(settings.smtp_from_email, [email], msg.as_string())
                sent += 1
            except Exception as exc:
                failed += 1
                errors.append(f"{email}: {exc}")

        server.quit()
    except Exception as exc:
        return sent, failed, [f"SMTP error: {exc}"]

    return sent, failed, errors


async def send_newsletter(run_id: str, group_ids: list[str] | None = None) -> dict[str, int | str]:
    """Send a completed newsletter to subscribers.

    Uses Resend API if RESEND_API_KEY is set, otherwise falls back to SMTP.
    If group_ids is provided, only sends to subscribers in those groups.

    Returns {"sent": N, "failed": N, "detail": "..."}.
    """
    has_resend = bool(settings.resend_api_key)
    has_smtp = bool(settings.smtp_host)

    if not has_resend and not has_smtp:
        return {"sent": 0, "failed": 0, "detail": "Email not configured — set RESEND_API_KEY or SMTP_HOST in env"}

    if group_ids:
        emails = await get_subscriber_emails_by_groups(group_ids)
        target_desc = f"{len(group_ids)} group(s)"
    else:
        emails = await get_subscriber_emails()
        target_desc = "all subscribers"

    if not emails:
        return {"sent": 0, "failed": 0, "detail": f"No subscribers in {target_desc}"}

    run = await get_run(run_id)
    if not run or not run.get("newsletter"):
        return {"sent": 0, "failed": 0, "detail": "Newsletter not found or incomplete"}

    newsletter_data = run["newsletter"]
    if isinstance(newsletter_data, str):
        newsletter_data = json.loads(newsletter_data)
    newsletter = Newsletter.model_validate(newsletter_data)
    config = run.get("config", {})
    if isinstance(config, str):
        config = json.loads(config)
    theme = config.get("theme", "Newsletter")

    html_body = to_html(newsletter)
    text_body = to_markdown(newsletter)
    subject = newsletter.title or f"Newsletter: {theme}"

    if has_resend:
        sent, failed, errors = await _send_via_resend(emails, subject, html_body, text_body)
    else:
        sent, failed, errors = await _send_via_smtp(emails, subject, html_body, text_body)

    detail = f"Sent to {sent} subscriber(s)"
    if failed:
        detail += f", {failed} failed"
    if errors:
        detail += " — " + "; ".join(errors[:3])
    return {"sent": sent, "failed": failed, "detail": detail}
