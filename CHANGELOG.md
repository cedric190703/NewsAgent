# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.0] — 2026-08-27

A hardening and completion release: the previously dead schedule feature now
works, two broken API contracts are fixed, and the offline provider became good
enough that the test suite exercises the real LLM paths.

### Fixed

- **Bookmarking was impossible from the UI.** `POST /api/runs/{id}/bookmarks`
  declared its fields as bare scalars, which FastAPI binds as *query*
  parameters, while the frontend sent a JSON body. Every save returned 422.
  All write endpoints now take explicit request models.
- **`POST /api/schedules` could not be called as documented.** It mixed a body
  model with scalar parameters, so `cron_expr` was a query parameter while
  `themes` and `config` were merged into one body. Now a single body model.
- **`PATCH /api/schedules/{id}`** took `enabled` as a query parameter; now a body.
- **Runs could be left stuck at `running` forever.** A client disconnect
  cancelled the SSE generator without recording a terminal state. Terminal
  status is now written from `finally`, and runs orphaned by a crash are retired
  at startup.
- **`/api/status` misreported live data.** It listed every *available* provider
  rather than those a run will actually use, so `SEARCH_PROVIDERS=mock` still
  claimed live data. It now reports the resolved set.
- **Loading a run from history showed every saved article as unsaved** — the UI
  never fetched that run's bookmarks.
- **The scheduler leaked in-flight runs on shutdown**, letting them execute
  against a closing database and HTTP client.
- Atom feeds with several `<link>` elements could take the `edit` link instead of
  the article; `<content:encoded>` bodies were ignored in favour of shorter
  descriptions.

### Added

- **A working scheduler.** The `schedules` table had no executor, so a saved
  schedule never produced anything. A background scheduler now ticks each
  minute, fires matching schedules with bounded concurrency, records each run
  against its schedule, and skips schedules that are still running.
- **A cron matcher** (`app/services/cron.py`) — 5-field syntax with ranges,
  steps, lists, month and weekday names, `@daily`-style aliases, and the vixie
  day-field OR quirk. No new dependency. Expressions are validated at the API
  edge.
- **`POST /api/schedules/{id}/run`** to fire a schedule immediately.
- **`/api/news/query` is real.** It previously returned placeholder text from
  stub agents ("Web search placeholder for X"). It now runs the same LangGraph
  pipeline as the streaming API and projects the result into the briefing shape,
  with a derived `confidence` and honest critic notes.
- **Feedback is persisted.** `POST /api/news/feedback` used to accept and
  discard. There is now a `feedback` table, a listing endpoint with a rating
  summary, and a rating widget in the UI.
- **`GET /api/ready`** with a per-dependency breakdown, including whether the
  configured Ollama model is actually pulled.
- **`GET /api/bookmarks`** — the reading list across all runs.
- Schedules panel, star-rating feedback bar, and a React error boundary in the UI.
- Structured logging, request IDs, request timing, and field-level validation
  errors.
- `Makefile`, GitHub Actions CI (lint, tests, pipeline smoke test, image build),
  and `docs/` covering architecture, API, configuration, development, operations.

### Changed

- **The offline provider returns schema-valid JSON.** It reads the JSON schema
  out of the prompt and synthesises a conforming instance — echoing ids back
  verbatim and quoting real article sentences. Previously it returned prose, so
  every node fell back to its heuristic and offline runs exercised only the
  fallback paths. Offline runs now drive the real LLM branches.
- **Off-topic filler is gated out.** A generous model relevance score could drag
  an unrelated story above the threshold — a Porsche review surfaced under
  "climate technology" because its blurb said "technology". Topicality is now a
  hard gate: the theme must appear in an article's headline or lede, with the
  article body deliberately ignored. A widened retry relaxes the requirement, so
  the first pass buys precision and the retry buys back recall.
- **Feed downloads are cached and single-flighted.** A 4-sub-topic run over 8
  feeds made 32 identical HTTP requests; it now makes 8.
- Article extraction is cached per URL and scoped to the page's `<article>` or
  `<main>` landmark, so navigation and footers no longer pollute scoring and
  quoting.
- One pooled HTTP client process-wide; one SQLite connection in WAL mode with
  indexes, replacing open/close-per-query.
- Ollama provider retries transient failures and can report health.
- List settings accept CSV as well as JSON.
- Docker image runs as a non-root user with a healthcheck; Compose waits for it.
- Backend tests: 2 → 294.

### Security

- **SSRF guard on all outbound fetches.** Article URLs come from third-party
  feeds and search APIs. Targets resolving to loopback, private, link-local
  (including cloud metadata), multicast or reserved addresses are refused, a
  hostname resolving to any private address is refused, and redirects are
  followed manually and re-checked at every hop.
- Response size cap and a global outbound concurrency budget.
- HTML export escapes all interpolations including attribute values; only
  `http(s)` URLs become links. Markdown export escapes link syntax.

### Removed

- The placeholder agent pipeline (`app/agents/`, `services/pipeline.py`,
  `content_processor.py`, `response_formatter.py`). It duplicated the LangGraph
  pipeline and returned stub text; `/api/news/query` now uses the real graph.

## [0.2.0]

LangGraph pipeline, live RSS retrieval, SSE streaming, UI redesign.

## [0.1.0]

Initial project scaffold.
