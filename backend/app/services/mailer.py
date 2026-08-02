"""Send newsletters via SMTP to the mailing list."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.graph.state import Newsletter
from app.services.exporter import to_html, to_markdown
from app.services.store import get_subscriber_emails, get_run


async def send_newsletter(run_id: str) -> dict[str, int | str]:
    """Send a completed newsletter to all subscribers via SMTP.

    Returns {"sent": N, "failed": N, "detail": "..."}.
    """
    if not settings.smtp_host:
        return {"sent": 0, "failed": 0, "detail": "SMTP not configured — set SMTP_HOST in env"}

    emails = await get_subscriber_emails()
    if not emails:
        return {"sent": 0, "failed": 0, "detail": "No subscribers in the mailing list"}

    run = await get_run(run_id)
    if not run or not run.get("newsletter"):
        return {"sent": 0, "failed": 0, "detail": "Newsletter not found or incomplete"}

    newsletter = Newsletter.model_validate(run["newsletter"])
    config = run.get("config", {})
    theme = config.get("theme", "Newsletter")

    html_body = to_html(newsletter)
    text_body = to_markdown(newsletter)

    subject = newsletter.title or f"Newsletter: {theme}"

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
        return {"sent": sent, "failed": failed, "detail": f"SMTP error: {exc}"}

    detail = f"Sent to {sent} subscriber(s)"
    if failed:
        detail += f", {failed} failed"
    if errors:
        detail += " — " + "; ".join(errors[:3])
    return {"sent": sent, "failed": failed, "detail": detail}
