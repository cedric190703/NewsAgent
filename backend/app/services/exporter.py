"""Newsletter export: Markdown, email-ready HTML, and PDF.

Newsletter text originates from third-party article bodies by way of the model,
so every interpolation into HTML is escaped, and only `http(s)` URLs are turned
into links — a `javascript:` href smuggled in from a source must not survive
into an exported file someone opens in a browser.
"""

from __future__ import annotations

import html
from datetime import datetime
from urllib.parse import urlsplit

from app.graph.state import Newsletter

SAFE_SCHEMES = frozenset({"http", "https"})


class ExportError(RuntimeError):
    """The requested export format is unavailable in this deployment."""


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _safe_url(url: str) -> str | None:
    try:
        scheme = urlsplit(url).scheme.lower()
    except ValueError:
        return None
    return url if scheme in SAFE_SCHEMES else None


def _fmt_date(value: datetime | None, pattern: str = "%b %d, %Y") -> str:
    return value.strftime(pattern) if value else ""


# --- markdown ------------------------------------------------------------


def _md_escape(text: str) -> str:
    """Neutralise the characters that would break out of a Markdown link/heading."""

    return (text or "").replace("[", "\\[").replace("]", "\\]").replace("\n", " ")


def to_markdown(newsletter: Newsletter) -> str:
    lines = [f"# {newsletter.title}"]
    if newsletter.subtitle:
        lines.append(f"*{newsletter.subtitle}*")
    lines += ["", newsletter.intro, ""]

    for section in newsletter.sections:
        lines.append(f"## {section.title}")
        if section.blurb:
            lines.append(section.blurb)
        for item in section.items:
            date = _fmt_date(item.published_at, "%Y-%m-%d") or "n/a"
            lines.append(f"\n### {item.headline}")
            lines.append(
                f"*{item.source_name} | {date} | score {item.scores.composite:.2f}*"
            )
            for bullet in item.bullets:
                lines.append(f"- {bullet}")
            for fact in item.key_facts:
                lines.append(f"  - **{_md_escape(fact.claim)}**")
                lines.append(f'    > "{fact.quote}"')
                url = _safe_url(fact.url)
                if url:
                    lines.append(f"    [{_md_escape(url)}]({url})")

    if newsletter.conflicts:
        lines.append("\n## ⚠ Flagged conflicts")
        for conflict in newsletter.conflicts:
            lines.append(
                f"- **[{conflict.severity}]** {conflict.claim} — {conflict.note}"
            )

    if newsletter.sources:
        lines.append("\n## Sources")
        for index, source in enumerate(newsletter.sources, start=1):
            url = _safe_url(source.url)
            label = _md_escape(source.source_name)
            link = f"[{label}]({url})" if url else label
            lines.append(f"{index}. {link} — {_md_escape(source.title)}")

    if newsletter.outro:
        lines += ["", newsletter.outro]

    if newsletter.notes:
        lines.append("\n---\n")
        lines += [f"- {note}" for note in newsletter.notes]

    lines.append(f"\n<!-- generated {newsletter.generated_at.isoformat()} -->")
    return "\n".join(lines)


# --- html ----------------------------------------------------------------

_STYLES = """
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         max-width: 720px; margin: 0 auto; padding: 24px; color: #1a1a2e;
         background: #fff; line-height: 1.6; }
  h1 { font-size: 1.8rem; margin-bottom: 0.25rem; }
  h3 { font-size: 1.3rem; margin-top: 2rem; border-bottom: 2px solid #e0e7ff;
       padding-bottom: 0.3rem; }
  h4 { font-size: 1.05rem; margin: 0 0 0.25rem; }
  .subtitle { color: #666; font-style: italic; margin-bottom: 1.5rem; }
  .cards { display: grid; gap: 1rem; }
  .card { border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; }
  .card-img { width: 100%; height: 180px; object-fit: cover; }
  .card-body { padding: 16px; }
  .meta { font-size: 0.8rem; color: #888; margin: 0 0 0.5rem; }
  .fact { margin: 0.75rem 0; padding: 0.5rem 0.75rem; background: #f8fafc;
          border-radius: 8px; }
  .fact blockquote { margin: 0.25rem 0; font-size: 0.85rem; color: #555;
                     border-left: 3px solid #a5b4fc; padding-left: 0.5rem; }
  .read-more { display: inline-block; margin-top: 0.5rem; color: #4f46e5;
               text-decoration: none; font-weight: 600; font-size: 0.85rem; }
  .notice { border-radius: 8px; padding: 0.6rem 0.9rem; font-size: 0.85rem;
            background: #fffbeb; color: #92400e; margin: 1rem 0; }
  ul { padding-left: 1.25rem; } li { margin: 0.25rem 0; }
  .sources { margin-top: 2rem; font-size: 0.85rem; }
  .footer { margin-top: 2.5rem; font-size: 0.75rem; color: #94a3b8; }
  @media (prefers-color-scheme: dark) {
    body { background: #0f172a; color: #e2e8f0; }
    .card { border-color: #1e293b; }
    .fact { background: #1e293b; }
    .fact blockquote { color: #94a3b8; }
    h3 { border-bottom-color: #1e293b; }
    .notice { background: #422006; color: #fcd34d; }
  }
"""


def _link(url: str, label: str, css_class: str = "") -> str:
    safe = _safe_url(url)
    if not safe:
        return _esc(label)
    attr = f' class="{css_class}"' if css_class else ""
    return (
        f'<a href="{_esc(safe)}" target="_blank" rel="noopener noreferrer"{attr}>'
        f"{_esc(label)}</a>"
    )


def _card_html(item) -> str:
    image = _safe_url(item.image_url or "")
    img = (
        f'<img src="{_esc(image)}" alt="" class="card-img" loading="lazy" />'
        if image
        else ""
    )
    bullets = "".join(f"<li>{_esc(bullet)}</li>" for bullet in item.bullets)
    facts = "".join(
        f'<div class="fact"><p>{_esc(fact.claim)}</p>'
        f"<blockquote>&ldquo;{_esc(fact.quote)}&rdquo;</blockquote>"
        f"{_link(fact.url, 'Source')}</div>"
        for fact in item.key_facts
    )
    return (
        f'<article class="card">{img}<div class="card-body">'
        f"<h4>{_esc(item.headline)}</h4>"
        f'<p class="meta">{_esc(item.source_name)} &middot; '
        f"{_esc(_fmt_date(item.published_at))}</p>"
        f"<ul>{bullets}</ul>{facts}"
        f"{_link(item.url, 'Read article →', 'read-more')}"
        f"</div></article>"
    )


def to_html(newsletter: Newsletter) -> str:
    sections = "".join(
        f'<section class="nl-section"><h3>{_esc(section.title)}</h3>'
        f"<p>{_esc(section.blurb)}</p>"
        f'<div class="cards">{"".join(_card_html(item) for item in section.items)}</div>'
        f"</section>"
        for section in newsletter.sections
    )

    conflicts = ""
    if newsletter.conflicts:
        rows = "".join(
            f"<li><strong>[{_esc(conflict.severity)}]</strong> "
            f"{_esc(conflict.claim)} — {_esc(conflict.note)}</li>"
            for conflict in newsletter.conflicts
        )
        conflicts = f"<section><h3>⚠ Flagged conflicts</h3><ul>{rows}</ul></section>"

    sources = ""
    if newsletter.sources:
        rows = "".join(
            f"<li>{_link(source.url, source.source_name)} — {_esc(source.title)}</li>"
            for source in newsletter.sources
        )
        sources = f'<section class="sources"><h3>Sources</h3><ol>{rows}</ol></section>'

    notices = "".join(
        f'<div class="notice">{_esc(note)}</div>' for note in newsletter.notes
    )
    outro = f"<p>{_esc(newsletter.outro)}</p>" if newsletter.outro else ""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(newsletter.title)}</title>
<style>{_STYLES}</style></head>
<body>
<h1>{_esc(newsletter.title)}</h1>
<p class="subtitle">{_esc(newsletter.subtitle)}</p>
<p>{_esc(newsletter.intro)}</p>
{notices}
{sections}
{conflicts}
{outro}
{sources}
<p class="footer">Generated {_esc(_fmt_date(newsletter.generated_at, "%b %d, %Y %H:%M UTC"))}</p>
</body></html>"""


# --- pdf -----------------------------------------------------------------


def to_pdf(newsletter: Newsletter) -> bytes:
    """Render via WeasyPrint. Raises `ExportError` when it is not installed."""

    try:
        from weasyprint import HTML  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ExportError(
            "PDF export needs WeasyPrint, which is not installed. "
            "Run `pip install weasyprint` (it also needs system Pango/Cairo "
            "libraries), or export Markdown/HTML instead."
        ) from exc

    try:
        return HTML(string=to_html(newsletter)).write_pdf()
    except Exception as exc:  # WeasyPrint surfaces backend errors of many types
        raise ExportError(f"PDF rendering failed: {exc}") from exc
