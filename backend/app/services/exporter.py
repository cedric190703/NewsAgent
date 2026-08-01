"""Newsletter export: Markdown, email-ready HTML, and PDF."""

from __future__ import annotations

import html
from datetime import datetime

from app.graph.state import Newsletter


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
            date = item.published_at.strftime("%Y-%m-%d") if item.published_at else "n/a"
            lines.append(f"\n### {item.headline}")
            lines.append(f"*{item.source_name} | {date} | score {item.scores.composite:.2f}*")
            for bullet in item.bullets:
                lines.append(f"- {bullet}")
            for fact in item.key_facts:
                lines.append(f"  - **{fact.claim}**")
                lines.append(f'    > "{fact.quote}"')
                lines.append(f"    [{fact.url}]({fact.url})")

    if newsletter.conflicts:
        lines.append("\n## ⚠ Flagged conflicts")
        for conflict in newsletter.conflicts:
            lines.append(f"- **[{conflict.severity}]** {conflict.claim} — {conflict.note}")

    lines.append("\n## Sources")
    for i, source in enumerate(newsletter.sources, 1):
        lines.append(f"{i}. [{source.source_name}]({source.url}) — {source.title}")

    if newsletter.notes:
        lines.append("\n---\n")
        for note in newsletter.notes:
            lines.append(f"- {note}")

    return "\n".join(lines)


def to_html(newsletter: Newsletter) -> str:
    def esc(text: str) -> str:
        return html.escape(text)

    def fmt_date(dt: datetime | None) -> str:
        return dt.strftime("%b %d, %Y") if dt else ""

    items_html = []
    for section in newsletter.sections:
        cards = []
        for item in section.items:
            img = (
                f'<img src="{esc(item.image_url)}" alt="" class="card-img" '
                'loading="lazy" />'
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
            cards.append(
                f'<article class="card">{img}'
                f'<div class="card-body">'
                f'<h4>{esc(item.headline)}</h4>'
                f'<p class="meta">{esc(item.source_name)} &middot; {fmt_date(item.published_at)}</p>'
                f"<ul>{bullets}</ul>"
                f"{facts}"
                f'<a href="{esc(item.url)}" target="_blank" rel="noopener" class="read-more">Read article &rarr;</a>'
                f"</div></article>"
            )
        items_html.append(
            f'<section class="nl-section">'
            f"<h3>{esc(section.title)}</h3>"
            f"<p>{esc(section.blurb)}</p>"
            f'<div class="cards">{" ".join(cards)}</div>'
            f"</section>"
        )

    sources = "".join(
        f'<li><a href="{esc(s.url)}" target="_blank" rel="noopener">{esc(s.source_name)}</a> — {esc(s.title)}</li>'
        for s in newsletter.sources
    )

    conflicts = ""
    if newsletter.conflicts:
        conflicts = "<section><h3>⚠ Flagged conflicts</h3><ul>" + "".join(
            f"<li><strong>[{esc(c.severity)}]</strong> {esc(c.claim)} — {esc(c.note)}</li>"
            for c in newsletter.conflicts
        ) + "</ul></section>"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(newsletter.title)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 720px; margin: 0 auto; padding: 24px; color: #1a1a2e; line-height: 1.6; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 0.25rem; }}
  h2 {{ color: #6366f1; font-size: 1.1rem; font-weight: 600; }}
  h3 {{ font-size: 1.3rem; margin-top: 2rem; border-bottom: 2px solid #e0e7ff; padding-bottom: 0.3rem; }}
  h4 {{ font-size: 1.05rem; margin: 0 0 0.25rem; }}
  .subtitle {{ color: #666; font-style: italic; margin-bottom: 1.5rem; }}
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
<h1>{esc(newsletter.title)}</h1>
<p class="subtitle">{esc(newsletter.subtitle)}</p>
<p>{esc(newsletter.intro)}</p>
{" ".join(items_html)}
{conflicts}
<section class="sources"><h3>Sources</h3><ul>{sources}</ul></section>
</body></html>"""


def to_pdf(newsletter: Newsletter) -> bytes:
    """Generate PDF via weasyprint if available, else fall back to HTML bytes."""

    html_content = to_html(newsletter)
    try:
        from weasyprint import HTML  # type: ignore[import-untyped]

        return HTML(string=html_content).write_pdf()  # type: ignore[no-any-return]
    except ImportError:
        raise RuntimeError(
            "weasyprint is not installed. Install it to enable PDF export: "
            "pip install weasyprint"
        )
