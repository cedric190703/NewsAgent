"""CLI harness to inspect a graph run without the UI.

    python -m app.graph.harness --theme "ocean restoration" --mode uplifting
    python -m app.graph.harness --theme "AI safety" --json out.json
    python -m app.graph.harness --print-graph
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.core.logging import configure_logging
from app.graph.builder import TOPOLOGY, build_graph
from app.graph.runner import events_from, new_run_id, stream_run
from app.graph.state import (
    GoodNewsMode,
    Length,
    NewsletterState,
    RunConfig,
    Tone,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the newsletter graph.")
    parser.add_argument("--theme", default="urban air quality improvements")
    parser.add_argument("--also", action="append", default=[], help="extra theme")
    parser.add_argument("--days", type=int, default=14, help="date range in days")
    parser.add_argument("--subtopics", type=int, default=3)
    parser.add_argument("--max-sources", type=int, default=8)
    parser.add_argument(
        "--mode",
        choices=[m.value for m in GoodNewsMode],
        default=GoodNewsMode.BALANCED.value,
    )
    parser.add_argument("--tone", choices=[t.value for t in Tone], default=Tone.NEUTRAL.value)
    parser.add_argument(
        "--length", choices=[length.value for length in Length], default=Length.STANDARD.value
    )
    parser.add_argument("--providers", default="", help="comma list, e.g. mock,tavily")
    parser.add_argument("--no-factcheck", action="store_true")
    parser.add_argument("--json", dest="json_path", default=None)
    parser.add_argument("--print-graph", action="store_true")
    parser.add_argument("--ephemeral", action="store_true", help="no sqlite checkpoint")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser.parse_args()


def _print_graph() -> None:
    graph = build_graph()
    print("\nNodes:")
    for node in TOPOLOGY["nodes"]:
        print(f"  {node['id']:<18} {node['kind']:<11} {node['description']}")
    print("\nEdges:")
    for edge in TOPOLOGY["edges"]:
        label = f" [{edge.get('label')}]" if edge.get("label") else ""
        print(f"  {edge['source']:<18} -> {edge['target']:<18} {edge['kind']}{label}")
    try:
        print("\nMermaid:\n")
        print(graph.get_graph().draw_mermaid())
    except Exception as exc:  # optional dependency path
        print(f"(mermaid rendering unavailable: {exc})")


def _render(state: NewsletterState) -> str:
    newsletter = state.get("newsletter")
    if newsletter is None:
        return "No newsletter was produced."

    lines = [f"\n{'=' * 72}", newsletter.title.upper()]
    if newsletter.subtitle:
        lines.append(newsletter.subtitle)
    lines += ["=" * 72, "", newsletter.intro, ""]

    for section in newsletter.sections:
        lines.append(f"\n## {section.title}")
        if section.blurb:
            lines.append(section.blurb)
        for item in section.items:
            date = item.published_at.date().isoformat() if item.published_at else "n/a"
            lines.append(f"\n  * {item.headline}")
            lines.append(f"    {item.source_name} | {date} | score {item.scores.composite:.2f}")
            for bullet in item.bullets:
                lines.append(f"      - {bullet}")
            for fact in item.key_facts:
                lines.append(f"      [fact] {fact.claim}")
                lines.append(f'        "{fact.quote[:120]}"')
                lines.append(f"        {fact.url}")

    if newsletter.conflicts:
        lines.append("\n## Flagged conflicts")
        for conflict in newsletter.conflicts:
            lines.append(f"  ! [{conflict.severity}] {conflict.claim} - {conflict.note}")

    lines.append("\n## Sources")
    for index, source in enumerate(newsletter.sources, start=1):
        lines.append(f"  {index}. {source.source_name}: {source.url}")

    if newsletter.notes:
        lines.append("\n## Notes")
        lines += [f"  - {note}" for note in newsletter.notes]

    return "\n".join(lines)


async def _main() -> None:
    args = _parse_args()
    configure_logging("DEBUG" if args.verbose else "WARNING", settings.json_logs)
    if args.print_graph:
        _print_graph()
        return

    now = datetime.now(timezone.utc)
    config = RunConfig(
        theme=args.theme,
        extra_themes=args.also,
        subtopic_count=args.subtopics,
        date_from=now - timedelta(days=args.days),
        date_to=now,
        max_sources=args.max_sources,
        tone=Tone(args.tone),
        length=Length(args.length),
        good_news_mode=GoodNewsMode(args.mode),
        enable_factcheck=not args.no_factcheck,
        providers=[p.strip() for p in args.providers.split(",") if p.strip()],
    )

    run_id = new_run_id()
    print(f"run_id={run_id}  theme={config.theme!r}  mode={config.good_news_mode.value}")
    print("-" * 72)

    final: dict[str, Any] = {}
    async for node, update in stream_run(
        config, run_id=run_id, persistent=not args.ephemeral
    ):
        for evt in events_from(update):
            branch = f" ({evt.branch[:8]})" if evt.branch else ""
            counts = f" {evt.counts}" if evt.counts else ""
            print(f"[{evt.status:<7}] {evt.node}{branch}: {evt.detail}{counts}")
        for error in (update or {}).get("errors") or []:
            print(f"[error  ] {error}")
        final.setdefault("nodes", []).append(node)
        if (update or {}).get("newsletter") is not None:
            final["newsletter"] = update["newsletter"]
        for key in ("raw_articles", "scored", "summaries", "subtopics", "conflicts"):
            if (update or {}).get(key):
                final[key] = update[key]

    state: NewsletterState = final  # type: ignore[assignment]
    print(_render(state))

    if args.json_path:
        payload = {
            "run_id": run_id,
            "config": config.model_dump(mode="json"),
            "newsletter": (
                final["newsletter"].model_dump(mode="json")
                if final.get("newsletter") is not None
                else None
            ),
        }
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str)
        print(f"\nWrote {args.json_path}")


async def _run() -> None:
    from app.core.http import close_client

    try:
        await _main()
    finally:
        await close_client()


if __name__ == "__main__":
    asyncio.run(_run())
