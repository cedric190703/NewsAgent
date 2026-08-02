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
from app.services.store import (
    get_subscriber_emails,
    get_subscriber_emails_by_groups,
    get_run,
    record_delivery,
    get_subscriber_with_groups_by_email,
)

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


def _combine_newsletters_html(items: list[tuple[str, Newsletter]]) -> str:
    """Combine multiple newsletters into one HTML email, sequentially by group."""
    import html as _html

    def esc(text: str) -> str:
        return _html.escape(text)

    sections_html = []
    for group_name, nl in items:
        cards = []
        for section in nl.sections:
            card_items = []
            for item in section.items:
                img = (
                    f'<img src="{esc(item.image_url)}" alt="" class="card-img" loading="lazy" />'
                    if item.image_url
                    else ""
                )
                bullets = "".join(f"<li>{esc(b)}</li>" for b in item.bullets)
                facts = "".join(
                    f'<div class="fact"><p>{esc(f.claim)}</p>'
                    f'<blockquote>&ldquo;{esc(f.quote)}&rdquo;</blockquote>'
                    f'<a href="{esc(f.url)}" target="_blank" rel="noopener">Source</a></div>'
                    for f in item.key_facts
                )
                card_items.append(
                    f'<article class="card">{img}'
                    f'<div class="card-body">'
                    f'<h4>{esc(item.headline)}</h4>'
                    f'<p class="meta">{esc(item.source_name)} &middot; {item.published_at.strftime("%b %d, %Y") if item.published_at else ""}</p>'
                    f"<ul>{bullets}</ul>"
                    f"{facts}"
                    f'<a href="{esc(item.url)}" target="_blank" rel="noopener" class="read-more">Read article &rarr;</a>'
                    f"</div></article>"
                )
            sections_html.append(
                f'<section class="nl-section">'
                f"<h3>{esc(section.title)}</h3>"
                f"<p>{esc(section.blurb)}</p>"
                f'<div class="cards">{" ".join(card_items)}</div>'
                f"</section>"
            )

    all_sources = []
    for _, nl in items:
        for s in nl.sources:
            all_sources.append(s)
    sources_html = "".join(
        f'<li><a href="{esc(s.url)}" target="_blank" rel="noopener">{esc(s.source_name)}</a> — {esc(s.title)}</li>'
        for s in all_sources
    )

    group_labels = " + ".join(g for g, _ in items)
    title = f"Your Newsletter — {group_labels}"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 720px; margin: 0 auto; padding: 24px; color: #1a1a2e; line-height: 1.6; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 0.25rem; }}
  h2 {{ color: #6366f1; font-size: 1.1rem; font-weight: 600; }}
  h3 {{ font-size: 1.3rem; margin-top: 2rem; border-bottom: 2px solid #e0e7ff; padding-bottom: 0.3rem; }}
  h4 {{ font-size: 1.05rem; margin: 0 0 0.25rem; }}
  .group-divider {{ border: 0; border-top: 2px dashed #cbd5e1; margin: 2.5rem 0; }}
  .group-label {{ background: #f1f5f9; border-radius: 8px; padding: 0.5rem 1rem; font-size: 0.85rem; font-weight: 600; color: #475569; margin-bottom: 1rem; }}
  .cards {{ display: grid; gap: 1rem; }}
  .card {{ border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; }}
  .card-img {{ width: 100%; height: 180px; object-fit: cover; }}
  .card-body {{ padding: 16px; }}
  .meta {{ font-size: 0.8rem; color: #888; margin: 0 0 0.5rem; }}
  .fact {{ margin: 0.75rem 0; padding: 0.5rem 0.75rem; background: #f8fafc; border-radius: 8px; }}
  .fact blockquote {{ margin: 0.25rem 0; font-size: 0.85rem; color: #555; border-left: 3px solid #a5b4fc; padding-left: 0.5rem; }}
  .read-more {{ display: inline-block; margin-top: 0.5rem; color: #6366f1; text-decoration: none; font-weight: 600; font-size: 0.85rem; }}
  ul {{ padding-left: 1.25rem; }} li {{ margin: 0.25rem 0; }}
  .sources {{ margin-top: 2rem; font-size: 0.85rem; }}
</style></head>
<body>
<h1>{esc(title)}</h1>
{"<hr class='group-divider' />".join(
    f'<div class="group-label">{esc(g)}</div><p>{esc(nl.intro)}</p>' + "".join(
        f'<section class="nl-section"><h3>{esc(s.title)}</h3><p>{esc(s.blurb)}</p>'
        f'<div class="cards">' + "".join(
            f'<article class="card">' +
            (f'<img src="{esc(item.image_url)}" alt="" class="card-img" loading="lazy" />' if item.image_url else "") +
            f'<div class="card-body"><h4>{esc(item.headline)}</h4>'
            f'<p class="meta">{esc(item.source_name)} &middot; {item.published_at.strftime("%b %d, %Y") if item.published_at else ""}</p>'
            f'<ul>{"".join(f"<li>{esc(b)}</li>" for b in item.bullets)}</ul>'
            f'<a href="{esc(item.url)}" target="_blank" rel="noopener" class="read-more">Read article &rarr;</a>'
            f"</div></article>"
            for item in s.items
        ) + f'</div></section>'
        for s in nl.sections
    )
    for g, nl in items
)}
<section class="sources"><h3>Sources</h3><ul>{sources_html}</ul></section>
</body></html>"""


def _combine_newsletters_markdown(items: list[tuple[str, Newsletter]]) -> str:
    """Combine multiple newsletters into one markdown text, sequentially by group."""
    lines: list[str] = []
    group_labels = " + ".join(g for g, _ in items)
    lines.append(f"# Your Newsletter — {group_labels}")
    lines.append("")

    for group_name, nl in items:
        lines.append(f"\n---\n## [{group_name}] {nl.title}")
        if nl.subtitle:
            lines.append(f"*{nl.subtitle}*")
        lines += ["", nl.intro, ""]
        for section in nl.sections:
            lines.append(f"### {section.title}")
            if section.blurb:
                lines.append(section.blurb)
            for item in section.items:
                date = item.published_at.strftime("%Y-%m-%d") if item.published_at else "n/a"
                lines.append(f"\n#### {item.headline}")
                lines.append(f"*{item.source_name} | {date} | score {item.scores.composite:.2f}*")
                for bullet in item.bullets:
                    lines.append(f"- {bullet}")

    lines.append("\n## Sources")
    for i, s in enumerate(sum((nl.sources for _, nl in items), []), 1):
        lines.append(f"{i}. [{s.source_name}]({s.url}) — {s.title}")

    return "\n".join(lines)


async def send_newsletter(run_id: str, group_ids: list[str] | None = None) -> dict[str, int | str]:
    """Send a completed newsletter to subscribers.

    Uses Resend API if RESEND_API_KEY is set, otherwise falls back to SMTP.
    If group_ids is provided, only sends to subscribers in those groups.

    For subscribers in multiple selected groups, combines all group newsletters
    into one email with sequential sections.

    Returns {"sent": N, "failed": N, "detail": "..."}.
    """
    has_resend = bool(settings.resend_api_key)
    has_smtp = bool(settings.smtp_host)

    if not has_resend and not has_smtp:
        return {"sent": 0, "failed": 0, "detail": "Email not configured — set RESEND_API_KEY or SMTP_HOST in env"}

    # Get the current run's newsletter
    run = await get_run(run_id)
    if not run or not run.get("newsletter"):
        return {"sent": 0, "failed": 0, "detail": "Newsletter not found or incomplete"}

    newsletter_data = run["newsletter"]
    if isinstance(newsletter_data, str):
        newsletter_data = json.loads(newsletter_data)
    current_nl = Newsletter.model_validate(newsletter_data)
    config = run.get("config", {})
    if isinstance(config, str):
        config = json.loads(config)
    current_theme = config.get("theme", "Newsletter")

    # Get group names for the current run's groups
    from app.services.store import list_groups
    all_groups = await list_groups()
    group_name_map = {g["group_id"]: g["name"] for g in all_groups}
    current_group_names = [group_name_map.get(gid, gid) for gid in (group_ids or [])]

    if group_ids:
        emails = await get_subscriber_emails_by_groups(group_ids)
        target_desc = f"{len(group_ids)} group(s)"
    else:
        emails = await get_subscriber_emails()
        target_desc = "all subscribers"

    if not emails:
        return {"sent": 0, "failed": 0, "detail": f"No subscribers in {target_desc}"}

    sent = 0
    failed = 0
    errors: list[str] = []

    for email in emails:
        # For each subscriber, check if they belong to multiple selected groups
        subscriber_info = await get_subscriber_with_groups_by_email(email)
        if not subscriber_info:
            continue

        # Find which of the subscriber's groups are in the current send
        subscriber_group_ids = {g["group_id"] for g in subscriber_info.get("groups", [])}
        relevant_group_ids = set(group_ids or []) & subscriber_group_ids

        if not relevant_group_ids:
            # Subscriber not in any selected group — skip
            continue

        if len(relevant_group_ids) <= 1:
            # Single group — send the newsletter as-is
            html_body = to_html(current_nl)
            text_body = to_markdown(current_nl)
            subject = current_nl.title or f"Newsletter: {current_theme}"
        else:
            # Multiple groups — combine newsletters from all relevant group deliveries
            # Gather all delivered runs for this subscriber's relevant groups
            from app.services.store import _connect, _now
            db = await _connect()
            try:
                # Get all run_deliveries for the relevant groups, joined with runs
                placeholders = ",".join("?" * len(relevant_group_ids))
                cursor = await db.execute(
                    f"SELECT DISTINCT r.run_id, r.config, r.newsletter, r.created_at "
                    f"FROM runs r "
                    f"INNER JOIN run_deliveries rd ON rd.run_id = r.run_id "
                    f"WHERE rd.group_id IN ({placeholders}) "
                    f"AND r.status IN ('done', 'partial') AND r.newsletter IS NOT NULL "
                    f"ORDER BY r.created_at DESC",
                    list(relevant_group_ids),
                )
                rows = await cursor.fetchall()
            finally:
                await db.close()

            # Build (group_name, Newsletter) pairs — include current run
            items: list[tuple[str, Newsletter]] = []
            seen_runs = set()
            for row in rows:
                rid = row["run_id"]
                if rid in seen_runs:
                    continue
                seen_runs.add(rid)
                nl_data = json.loads(row["newsletter"]) if row["newsletter"] else None
                if not nl_data:
                    continue
                try:
                    nl = Newsletter.model_validate(nl_data)
                except Exception:
                    continue
                # Get the group name for this delivery
                cfg = json.loads(row["config"]) if row["config"] else {}
                theme = cfg.get("theme", "Newsletter")
                items.append((theme, nl))

            # Make sure current run is included
            if run_id not in seen_runs:
                items.append((current_theme, current_nl))

            if not items:
                continue

            html_body = _combine_newsletters_html(items)
            text_body = _combine_newsletters_markdown(items)
            group_labels = " + ".join(g for g, _ in items)
            subject = f"Your Newsletter — {group_labels}"

        # Send to this subscriber
        if has_resend:
            s, f_, errs = await _send_via_resend([email], subject, html_body, text_body)
        else:
            s, f_, errs = await _send_via_smtp([email], subject, html_body, text_body)
        sent += s
        failed += f_
        errors.extend(errs)

    if sent > 0 and group_ids:
        await record_delivery(run_id, group_ids)

    detail = f"Sent to {sent} subscriber(s)"
    if failed:
        detail += f", {failed} failed"
    if errors:
        detail += " — " + "; ".join(errors[:3])
    return {"sent": sent, "failed": failed, "detail": detail}
