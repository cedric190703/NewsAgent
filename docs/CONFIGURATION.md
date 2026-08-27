# Configuration

Every setting is an environment variable, read once at startup into a Pydantic
`Settings` object (`app/core/config.py`). **Every one has a working default**, so
the app runs with no `.env` file at all.

Load order: process environment → `backend/.env` → defaults. Unknown variables
are ignored.

## List values

List-valued settings accept either form, so a `.env` stays readable:

```bash
SEARCH_PROVIDERS=rss,tavily
SEARCH_PROVIDERS=["rss","tavily"]
```

---

## Application

| Variable | Default | Notes |
|---|---|---|
| `APP_NAME` | `AI News Agent` | Shown in the OpenAPI docs |
| `APP_VERSION` | `0.3.0` | Reported by `/api/health` |
| `ENVIRONMENT` | `local` | `local`, `test`, or `production` |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed browser origins |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `JSON_LOGS` | `false` | `true` for structured one-line-per-event JSON |

## Language model

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` or `mock` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Docker Compose uses `host.docker.internal` |
| `OLLAMA_MODEL` | `mistral:latest` | Must be pulled: `ollama pull mistral` |
| `LLM_TIMEOUT_SECONDS` | `60` | Per request. Local models are slow; 120+ is reasonable |
| `LLM_MAX_CONCURRENCY` | `4` | Parallel LLM calls. Lower it if Ollama thrashes |
| `LLM_TEMPERATURE` | `0.2` | Low on purpose — this is extraction, not creative writing |

`LLM_PROVIDER=mock` is not a stub returning prose. It reads the JSON schema out
of the prompt and returns a conforming instance, quoting real sentences from the
fetched article so the summarizer's verification passes. Offline runs therefore
exercise the same LLM branches a real model would.

## Search providers

| Variable | Default | Notes |
|---|---|---|
| `SEARCH_PROVIDERS` | `auto` | `auto`, or any of `rss`, `tavily`, `newsapi`, `mock` |
| `TAVILY_API_KEY` | — | Presence enables the provider |
| `TAVILY_SEARCH_DEPTH` | `basic` | `basic` or `advanced` (slower, costs more) |
| `NEWSAPI_KEY` | — | Presence enables the provider |
| `NEWSAPI_LANGUAGE` | `en` | ISO 639-1 code |
| `RSS_FEEDS` | 8 built-in feeds | Google News, BBC, Verge, Ars, Wired, Nature, Science, Guardian |

`auto` resolves to every provider that has credentials, falling back to the mock
if none do. RSS counts as configured whenever `RSS_FEEDS` is non-empty, so the
app has live data out of the box with no API keys.

Broad general-news feeds give poor precision on narrow themes. If your topic is
specific, add a real search provider or point `RSS_FEEDS` at domain-specific
feeds.

## Fetching and extraction

| Variable | Default | Notes |
|---|---|---|
| `SOURCE_FETCH_TIMEOUT_SECONDS` | `15` | Per outbound request |
| `HTTP_USER_AGENT` | `NewsAgent/0.3 (…)` | Sent on every fetch |
| `ENABLE_ARTICLE_EXTRACTION` | `true` | Off = summarise from snippets only, much faster |
| `MIN_CONTENT_CHARS` | `400` | Below this, the full page is fetched |
| `MAX_ARTICLE_CHARS` | `16000` | Extracted text is truncated here |
| `MAX_DOWNLOAD_BYTES` | `5000000` | Larger responses are discarded |
| `MAX_CONCURRENT_FETCHES` | `8` | Global ceiling on outbound requests |
| `FEED_CACHE_TTL_SECONDS` | `300` | Feeds are shared across research branches |
| `ARTICLE_CACHE_TTL_SECONDS` | `900` | Per-URL extraction cache |
| `ALLOW_PRIVATE_FETCH_TARGETS` | `false` | **Disables the SSRF guard** |

> `ALLOW_PRIVATE_FETCH_TARGETS=true` lets the backend fetch loopback, private,
> and link-local addresses. Article URLs come from third-party feeds and search
> APIs, so they are attacker-influenceable — enable this only for tests or a
> genuinely trusted intranet.

## Pipeline behaviour

| Variable | Default | Notes |
|---|---|---|
| `RESULTS_PER_SUBTOPIC` | `8` | Requested per provider per angle |
| `MIN_RELEVANT_RESULTS` | `4` | Below this the run widens and retries |
| `MAX_SEARCH_ATTEMPTS` | `2` | Total passes, including the first |
| `RELEVANCE_THRESHOLD` | `0.35` | Minimum blended relevance to be selectable |
| `MIN_TOPIC_TERMS` | `2` | Topic terms required in an article's headline/lede |
| `ENABLE_FACTCHECK` | `true` | Global kill switch; per-run config can also disable it |
| `GRAPH_RECURSION_LIMIT` | `50` | LangGraph super-step ceiling |

`MIN_TOPIC_TERMS` is the precision dial and the one worth understanding. It is
capped by how many terms the theme actually has, so a one-word theme requires
one and `"climate technology"` requires both. A widened retry relaxes it to a
single term — the strict pass buys precision, the retry buys back recall.

- Getting off-topic filler? Raise it, or use a more specific theme.
- Getting empty newsletters? Lower it to `1`, or set `0` to disable the gate.

## Scheduler

| Variable | Default | Notes |
|---|---|---|
| `ENABLE_SCHEDULER` | `true` | Runs saved schedules in-process |
| `SCHEDULER_TICK_SECONDS` | `60` | Cron resolution is one minute; do not raise this |

Run several API replicas and each would fire every schedule. Set
`ENABLE_SCHEDULER=false` on all but one.

## Storage

| Variable | Default | Notes |
|---|---|---|
| `DATA_DIR` | `./data` | Created at startup |
| `CHECKPOINT_DB` | `./data/checkpoints.sqlite` | LangGraph's own checkpointer |
| `RUNS_DB` | `./data/runs.sqlite` | Runs, bookmarks, feedback, schedules |
| `RUN_HISTORY_LIMIT` | `500` | Older runs are pruned at startup |

Both databases must live on a real filesystem — SQLite over NFS will corrupt.
In Docker they sit on the `backend-data` volume.

---

## Frontend

| Variable | Default | Notes |
|---|---|---|
| `VITE_PROXY_TARGET` | `http://127.0.0.1:8000` | Where the dev server proxies `/api` |
| `VITE_API_BASE_URL` | *(unset)* | Call the API directly, bypassing the proxy |

Leave `VITE_API_BASE_URL` unset for local development and Docker Compose. Set it
when the built frontend is served from a different origin than the API — and add
that origin to `CORS_ORIGINS` on the backend.

---

## Recipes

**Fully offline** — no model, no network, no keys:

```bash
LLM_PROVIDER=mock
SEARCH_PROVIDERS=mock
```

**Live data, no model:**

```bash
LLM_PROVIDER=mock
SEARCH_PROVIDERS=rss
```

**Fast iteration** — skip the slowest stage:

```bash
ENABLE_ARTICLE_EXTRACTION=false
RESULTS_PER_SUBTOPIC=4
```

**Highest quality:**

```bash
SEARCH_PROVIDERS=tavily,newsapi,rss
TAVILY_SEARCH_DEPTH=advanced
RESULTS_PER_SUBTOPIC=12
MIN_TOPIC_TERMS=2
```

**Production:**

```bash
ENVIRONMENT=production
JSON_LOGS=true
LOG_LEVEL=INFO
CORS_ORIGINS=https://news.example.com
```
