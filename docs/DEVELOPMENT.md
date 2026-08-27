# Development

## Setup

```bash
make install    # backend venv + npm install
make test       # 294 backend tests, ~1.5s
make lint       # ruff + tsc
```

Without `make`, see the collapsed section in the [README](../README.md).

## Working offline

The whole system runs with no model, no API keys, and no network:

```bash
cd backend
LLM_PROVIDER=mock SEARCH_PROVIDERS=mock python -m app.graph.harness \
    --theme "coral reef restoration" --subtopics 2 --ephemeral
```

`MockProvider` is worth understanding, because it is why the test suite is
meaningful. Every node asks the model for structured JSON and falls back to a
heuristic when it cannot comply — so a mock returning prose would exercise only
the *fallback* paths, which is the opposite of what a test provider is for.

Instead it reads the JSON schema that `try_json` appends to the prompt and
synthesises a conforming instance, with field-name heuristics where correctness
depends on them:

- `id` / `subtopic_id` are echoed back verbatim, because the curator and
  composer match on them.
- `quote` returns a real sentence from the article text, so the summarizer's
  verbatim-quote check passes the way it would with a real model.
- Sibling list items vary by position, so a list is not the same object N times.

Offline runs therefore log `via LLM`, `llm_judged: 16` and `(llm)` — the real
branches — not the heuristic ones.

## The CLI harness

Inspect the pipeline without the UI:

```bash
python -m app.graph.harness --print-graph                    # topology + mermaid
python -m app.graph.harness --theme "ocean restoration" --mode uplifting
python -m app.graph.harness --theme "AI safety" --json out.json
python -m app.graph.harness --theme "X" --providers rss -v   # debug logging
```

| Flag | Purpose |
|---|---|
| `--theme` / `--also` | Primary theme, and extra themes in one newsletter |
| `--subtopics` / `--max-sources` | Breadth and depth |
| `--mode` / `--tone` / `--length` | Curation dial and output shape |
| `--providers` | Comma list, e.g. `rss` or `mock` |
| `--days` | Date window |
| `--no-factcheck` | Skip the cross-check stage |
| `--ephemeral` | No SQLite checkpoint |
| `-v` | Debug logging |

## Layout

```
backend/app/
├── core/
│   ├── config.py     Settings, one object, env-driven
│   ├── logging.py    Human-readable locally, JSON in production
│   ├── http.py       Pooled client + SSRF guard + global fetch budget
│   ├── cache.py      Async TTL cache with single-flight
│   └── text.py       Term extraction shared by search and scoring
├── providers/        LLM providers behind one Protocol
├── search/           Search providers behind one Protocol
├── graph/
│   ├── state.py      Every hand-off as a Pydantic model, plus fan-in reducers
│   ├── scoring.py    Deterministic scoring; no model involved
│   ├── llm.py        Structured JSON calls that fail gracefully
│   ├── nodes/        One module per node
│   ├── builder.py    Wiring, fan-out, conditional edges, TOPOLOGY
│   ├── runner.py     Streaming iterator + checkpointer lifecycle
│   └── harness.py    The CLI above
├── services/         store, scheduler, cron, exporter, briefing
└── api/              FastAPI routers + request/response models
```

Dependencies point strictly downward: `api → services → graph → search → core`.
`search` must never import from `graph` — that is why term extraction lives in
`core/text.py` rather than `graph/scoring.py`.

## Tests

```bash
.venv/bin/python -m pytest                      # everything
.venv/bin/python -m pytest tests/test_graph.py  # one file
.venv/bin/python -m pytest -k topicality        # by name
```

`pytest-asyncio` runs in auto mode, so `async def test_…` needs no decorator.

`tests/conftest.py` sets the environment **before** importing anything under
`app.`, because settings are read into a module-level singleton at import time.
It is the only reliable place to do that. Each test also gets its own SQLite
files via an autouse fixture, so ordering cannot leak state.

Fixtures: `client` (ASGI client running the app's real lifespan), `db` (an
initialised store), `run_config`, and the `make_article` / `make_summary` /
`make_newsletter` builders.

| File | Covers |
|---|---|
| `test_graph.py` | End-to-end runs, reducers, routing, fan-out, the topicality gate |
| `test_scoring.py` | All five scoring axes and the mode weighting |
| `test_text.py` | Term extraction and the on-topic requirement |
| `test_api_runs.py` | Runs, SSE, history, bookmarks, export |
| `test_api_schedules.py` | Schedule CRUD and cron validation |
| `test_api_news.py` | Briefing endpoint and feedback |
| `test_scheduler.py` | Due detection, execution, lifecycle |
| `test_cron.py` | The cron matcher, including the day-field OR quirk |
| `test_http_guard.py` | SSRF blocking |
| `test_rss.py` | Feed parsing, filtering, and the feed cache |
| `test_exporter.py` | Escaping and URL-scheme filtering |
| `test_store.py` | Persistence |
| `test_llm.py` | JSON coaxing and the graceful-failure contract |
| `test_mock_provider.py` | Schema compliance of the offline provider |
| `test_cache.py` | TTL and single-flight |

## Adding a search provider

1. Implement the `SearchProvider` protocol in `app/search/` — a `name` and an
   `async search(query) -> list[SearchHit]`. **Return `[]` on failure; never
   raise.** `multi_search` isolates providers, but a well-behaved one does not
   rely on that.
2. Fetch through `app.core.http.fetch`, never a bare `httpx` client — that is
   what applies the SSRF guard, the connection pool, and the fetch budget.
3. Register it in `app/search/registry.py`: add the name to `KNOWN_PROVIDERS`
   and a branch in `build_provider` that returns `None` without credentials.
4. If it returns only snippets, call `enrich_hits` to back-fill article bodies.
5. Add a test with a recorded payload; do not hit the network in tests.

## Adding an LLM provider

Implement `app.providers.base.LLMProvider` — a `name` and `async generate(
messages, *, json_mode) -> str` — then add a branch to `get_llm_provider` and a
literal to the `llm_provider` setting. Provide `aclose()` if you hold a client,
and `health()` if you can report reachability to `/api/ready`.

Prompting is not your concern: `app/graph/llm.py` appends the JSON schema, parses
fenced or bare JSON, retries once on a validation failure, and returns `None` on
anything else.

## Conventions

- **Typed hand-offs.** Nothing crosses a node boundary as free text.
- **Graceful degradation.** A node that needs the model must have a heuristic
  fallback, and must record which one produced the output.
- **Explicit request bodies.** A bare scalar in a FastAPI signature becomes a
  *query* parameter — the bug that made bookmarking impossible from the UI.
  Every write endpoint takes a model.
- **Comments explain why.** The what is in the code.
