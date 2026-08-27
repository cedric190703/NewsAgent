# Operations

## Running it

```bash
docker compose up --build                     # Ollama on the host
LLM_PROVIDER=mock docker compose up --build   # no model at all
```

Compose starts the API on `:8000` and the UI on `:5173`. The frontend waits for
the backend's healthcheck before starting. The backend image runs as a non-root
user (uid 10001) and ships a `HEALTHCHECK` that polls `/api/health`.

The Compose frontend service runs the Vite **dev** server, which is right for
local use but not for production. For a real deployment, build the static bundle
(`npm run build`) and serve `frontend/dist/` from any static host or CDN, then
point it at the API with `VITE_API_BASE_URL` and add that origin to
`CORS_ORIGINS`.

## Probes

| Endpoint | Use |
|---|---|
| `/api/health` | Liveness. Cheap, no dependencies. |
| `/api/ready` | Readiness with a per-dependency breakdown. |
| `/api/status` | Effective configuration. |

`/api/ready` **always returns 200**, reporting `ready` or `degraded` in the body.
This is deliberate: the app stays usable on heuristic fallbacks when the LLM is
down, so failing the probe would remove a working service from a load balancer
for no reason. **Alert on the `status` field, not the HTTP code.**

```json
{
  "status": "degraded",
  "checks": {
    "database":  { "ok": true },
    "llm":       { "ok": false, "provider": "ollama", "reachable": false,
                   "error": "ConnectError", "model_available": false },
    "search":    { "ok": true, "providers": ["rss"] },
    "scheduler": { "ok": true, "running": true }
  }
}
```

For Ollama the check reports whether the daemon is reachable *and* whether the
configured model is actually pulled — a missing model is the more common
failure, and it looks identical to a working daemon otherwise.

## Logging

Human-readable by default, one line per event:

```
10:31:02 INFO  app.api.runs      run created  run=8f14e45f theme='coral reef restoration'
10:31:14 INFO  app.graph.runner  graph run complete  run=8f14e45f seconds=12.4
```

Set `JSON_LOGS=true` in production for structured output. Every HTTP response
carries an `X-Request-ID`; send your own header to correlate a client request
with server logs. SSE streams are not logged on completion — they stay open for
the whole run, so a duration would be meaningless.

`LOG_LEVEL=DEBUG` adds per-provider hit counts and timings, and reports blocked
or failed fetches individually.

## Storage

Two SQLite databases under `DATA_DIR`:

| File | Owner | Contents |
|---|---|---|
| `checkpoints.sqlite` | LangGraph | Graph super-steps, for resumption |
| `runs.sqlite` | This app | Runs, bookmarks, feedback, schedules |

Keeping them separate means the application schema can migrate without touching
framework-owned data. `runs.sqlite` runs in WAL mode so the SSE reader and the
scheduler writer coexist.

**Both must be on a real local filesystem.** SQLite over NFS or SMB will
corrupt. In Docker they live on the `backend-data` volume.

Back up with a live-safe copy:

```bash
sqlite3 data/runs.sqlite ".backup 'backup/runs-$(date +%F).sqlite'"
```

At startup the app applies additive schema migrations, retires runs left at
`running` by a crash or restart (they can never resume), and prunes history
beyond `RUN_HISTORY_LIMIT`.

## Scheduling

The scheduler runs in-process, ticking once a minute aligned to the top of the
minute. Enabled schedules whose cron expression matches fire, capped at two
concurrent runs; a schedule still running is skipped rather than queued, so a
slow model cannot let ticks pile into a thundering herd.

**With more than one API replica, every replica would fire every schedule.** Set
`ENABLE_SCHEDULER=false` on all but one.

Scheduled runs appear in history with `source: "schedule:{id}"` and are linked
back from the schedule's `last_run_id`. Verify one without waiting for its slot:

```bash
curl -X POST localhost:8000/api/schedules/{id}/run
```

On shutdown the scheduler cancels both its loop and any in-flight runs, marking
them `cancelled` — they hold the database and HTTP client, and leaving them
detached means they keep executing against resources shutdown is closing.

## Security

**Outbound requests are guarded.** Article URLs come from third-party feeds and
search APIs, so they are attacker-influenceable. `app/core/http.py` resolves each
target and refuses anything that is not a public address — loopback, private,
link-local (including the `169.254.169.254` cloud-metadata endpoint), multicast
and reserved ranges. A hostname resolving to *any* private address is refused,
closing the split-answer hole. Redirects are followed manually and re-checked at
every hop, because `follow_redirects=True` would let a public URL bounce the
request somewhere internal behind the guard's back.

`ALLOW_PRIVATE_FETCH_TARGETS=true` disables all of this. Use it only in tests or
a genuinely trusted intranet.

**Exports are escaped.** Newsletter text originates from third-party pages by way
of the model. HTML export escapes every interpolation including attribute
values, and only `http(s)` URLs become links — a `javascript:` href smuggled in
from a source must not survive into a file someone opens in a browser. Markdown
export escapes brackets so an injected `](…)` cannot terminate a link early.

**Responses are size-capped** at `MAX_DOWNLOAD_BYTES`, and outbound concurrency
is bounded by `MAX_CONCURRENT_FETCHES`.

**Not yet provided:** authentication, authorisation, rate limiting, and
multi-tenancy. The API is unauthenticated and single-tenant — anyone who can
reach it can read every run and create new ones. Put it behind your own
authenticating proxy, and do not expose it directly to the internet.

Set `CORS_ORIGINS` to your real frontend origin in production. The default only
allows `http://localhost:5173`.

## Cost and load

The expensive stages are LLM calls and article extraction.

- One run makes roughly `subtopic_count` planner calls, `ceil(articles / 5)`
  curator calls, one call per selected article, one fact-check call, and one
  composer call.
- `LLM_MAX_CONCURRENCY` bounds how many run at once. Local models thrash above
  2–4.
- `ENABLE_ARTICLE_EXTRACTION=false` is the single biggest speed-up, at the cost
  of summary quality — the summarizer then works from snippets.
- Feed downloads and article extractions are cached, so re-running the same
  theme within the TTL is much cheaper than the first run.

`POST /api/news/query` is bounded by `LLM_TIMEOUT_SECONDS × 12` and returns
`504` past that. Use the streaming API for long runs — it has no such ceiling.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Everything logs `heuristic`, never `LLM` | Ollama unreachable or model not pulled | Check `/api/ready`; `ollama pull mistral` |
| "no verifiable stories found" | Theme too narrow for the configured feeds | Widen the date range, lower `MIN_TOPIC_TERMS`, or add a search provider |
| Off-topic stories in the newsletter | Broad general feeds; the run widened | Raise `MIN_TOPIC_TERMS`, use domain-specific feeds, or add Tavily/NewsAPI |
| Newsletter notes say queries were broadened | First pass found too little — working as intended | Nothing, or narrow the theme |
| PDF export returns 501 | WeasyPrint absent | `pip install weasyprint` plus system Pango/Cairo |
| Runs stuck at `running` | Process died mid-run | They are retired at next startup |
| Schedules never fire | Scheduler disabled, or several replicas | Check `/api/status`; enable on exactly one replica |
| `504` from `/api/news/query` | Run exceeded the ceiling | Lower `depth`/`max_sources`, or use the streaming API |
