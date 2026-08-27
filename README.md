# AI News Agent

A multi-agent news intelligence platform. You give it a theme; it plans research
angles, searches real sources, scores and curates what it finds, summarises each
story with **verbatim quotes checked against the fetched article**, cross-checks
claims between sources, and composes a newsletter you can read, export, or
schedule.

The backend is Python + FastAPI with a [LangGraph](https://langchain-ai.github.io/langgraph/)
pipeline. The frontend is React + Vite. Model inference runs locally through
Ollama, behind a provider interface so hosted models can be added later.

![AI Newsletter Agent workflow](./medias/Schema-workflow-AI.png)

---

## Quick start

The fastest path needs no model, no API keys, and no network:

```bash
make install
make demo
```

`make demo` runs one full pipeline in your terminal using the offline providers.
To bring up the actual app:

```bash
make run-backend    # API on http://localhost:8000  (docs at /docs)
make run-frontend   # UI  on http://localhost:5173
```

Or with Docker:

```bash
LLM_PROVIDER=mock docker compose up --build   # no model needed
docker compose up --build                     # uses Ollama on the host
```

If you use the Ollama path, pull a model first: `ollama pull mistral`.

<details>
<summary>Without <code>make</code></summary>

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```
</details>

---

## What it actually does

A run is a directed graph, not a chain of prompts. Stages fan out in parallel
and rejoin, and a thin result loops back for a broader search.

```text
                    ┌─────────────┐
  theme ───────────▶│   Planner   │  theme -> N distinct research angles
                    └──────┬──────┘
                           │ fan out, one branch per angle
              ┌────────────┼────────────┐
              ▼            ▼            ▼
          ┌────────┐  ┌────────┐  ┌────────┐
          │Research│  │Research│  │Research│   real search providers
          └────┬───┘  └────┬───┘  └────┬───┘
               └───────────┼───────────┘  fan in, deduped by canonical URL
                           ▼
                    ┌─────────────┐
                    │   Curator   │  5 scoring axes + a hard topicality gate
                    └──────┬──────┘
             too thin ─────┤
                           │        ┌──────────────┐
                           ├───────▶│Widen Queries │──┐ (retry, capped)
                           │        └──────────────┘  │
                           │◀─────────────────────────┘
                           │ fan out, one branch per selected article
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │Summarizer│ │Summarizer│ │Summarizer│  every fact needs a real quote
        └─────┬────┘ └─────┬────┘ └─────┬────┘
              └────────────┼────────────┘
                           ▼
                    ┌─────────────┐
                    │  Fact-check │  dedupe + flag contradictions (optional)
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
                    │  Composer   │  assembles the newsletter
                    └──────┬──────┘
                           ▼
              UI · Markdown · HTML · PDF · schedule
```

Full detail in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

### The guarantees it tries to keep

- **No invented sources.** The composer only ever sees typed `ArticleSummary`
  objects, never raw article text, and any URL it emits that was not fetched is
  stripped before the newsletter ships.
- **No unverifiable facts.** Each key fact carries a quote that must appear
  verbatim in the fetched article. Quotes that do not match are dropped, and the
  newsletter reports how many were removed.
- **No silent failures.** Every node falls back to a deterministic heuristic if
  the model is unavailable, so a run degrades instead of crashing — and the
  output says which parts were heuristic.
- **No off-topic filler.** A story whose headline and lede never mention the
  theme cannot be selected, however confidently the model scored it.

### Curation dial

Two independent axes are measured on every article, then *weighted* differently
per mode — so re-ranking a run never means re-fetching it.

| Mode | What it favours |
|---|---|
| `uplifting` | constructive outcomes: progress, recovery, solutions |
| `high_signal` | substantive reporting: specific, sourced, low hype |
| `balanced` | both, evenly (default) |

---

## Configuration

Everything is environment variables; every one has a working default, so the app
runs with no `.env` at all. See **[backend/.env.example](backend/.env.example)**
for the annotated list and **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)** for
the reference.

The settings you are most likely to touch:

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `mock` runs the full graph with no model |
| `OLLAMA_MODEL` | `mistral:latest` | Local model name |
| `SEARCH_PROVIDERS` | `auto` | `auto`, or any of `rss`, `tavily`, `newsapi`, `mock` |
| `TAVILY_API_KEY` | — | Enables the Tavily provider |
| `NEWSAPI_KEY` | — | Enables the NewsAPI provider |
| `RSS_FEEDS` | 8 built-in feeds | Your own feed list (CSV or JSON) |
| `ENABLE_SCHEDULER` | `true` | Runs saved schedules in the background |

With no API keys the app uses the built-in RSS feeds. `/api/status` reports
which providers are live, and the UI shows a banner when it is on mock data.

---

## API

Interactive docs at `http://localhost:8000/docs`. Full reference in
**[docs/API.md](docs/API.md)**.

| Endpoint | Purpose |
|---|---|
| `POST /api/runs` → `GET /api/runs/{id}/stream` | Run with live SSE progress |
| `POST /api/news/query` | One structured briefing, synchronously |
| `GET /api/runs/{id}/export/{markdown\|html\|pdf}` | Download a newsletter |
| `POST /api/schedules` | Recurring newsletters on a cron expression |
| `POST /api/news/feedback` | Rate a result |
| `GET /api/health` · `/api/ready` · `/api/status` | Probes and effective config |

---

## Development

```bash
make test     # backend test suite
make lint     # ruff + tsc
make fmt      # apply safe lint fixes
```

Inspect a run without the UI:

```bash
cd backend
python -m app.graph.harness --theme "ocean restoration" --mode uplifting
python -m app.graph.harness --print-graph          # topology + mermaid
python -m app.graph.harness --theme "AI safety" --json out.json
```

`LLM_PROVIDER=mock` is not a stub that returns prose — it reads the JSON schema
out of the prompt and returns a conforming instance, quoting real sentences from
the fetched article. Offline runs therefore exercise the same LLM branches a
real model would. See **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)**.

---

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Graph topology, state, scoring, guarantees |
| [docs/API.md](docs/API.md) | Every endpoint, with request and response examples |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | All environment variables |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Setup, tests, layout, adding a provider |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Deployment, probes, storage, scheduling, security |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

---

## Status and roadmap

Working today: the full graph, live RSS / Tavily / NewsAPI retrieval, article
extraction, quote verification, cross-source fact-checking, SSE streaming,
run history, bookmarks, feedback, Markdown/HTML/PDF export, and cron schedules
executed by a background scheduler.

Not built yet:

- **RAG over a private knowledge base.** Needs an embedding model and a vector
  store; the retrieval interface is in place but there is no such provider.
- **Delivery beyond the browser.** Email and Slack; export and the API exist.
- **Hosted model providers.** The `LLMProvider` protocol is ready; only Ollama
  and the mock implement it.
- **Multi-user accounts.** Everything is currently single-tenant.

## License

No license has been chosen yet; all rights reserved by the author.
