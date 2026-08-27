# API reference

Base URL `http://localhost:8000`. Interactive docs at `/docs`, OpenAPI schema at
`/openapi.json`.

Every response carries an `X-Request-ID` header; send your own to correlate a
request with the server logs.

## Errors

Validation failures name the offending field rather than dumping a schema:

```json
{
  "detail": "Request validation failed",
  "errors": [
    { "field": "theme", "message": "String should have at least 3 characters",
      "type": "string_too_short" }
  ]
}
```

Other failures return `{"detail": "..."}`. Codes used: `400` bad format, `404`
unknown id, `409` not ready yet (exporting an unfinished run), `422` validation,
`500` pipeline failure, `501` PDF renderer absent, `504` briefing timed out.

---

## Two ways to run the pipeline

**Streaming** — create a run, then open its event stream. Use this when you want
progress. **Synchronous** — `POST /api/news/query` blocks and returns one
structured answer. Both execute the same graph.

---

## Runs

### `POST /api/runs` → `201`

Registers a run. Execution starts when you open the stream.

```jsonc
{
  "theme": "coral reef restoration",   // required, 3-500 chars
  "extra_themes": [],                  // additional themes in one newsletter
  "subtopic_count": 4,                 // 1-8 research angles
  "date_from": null,                   // ISO 8601, or null
  "date_to": null,
  "max_sources": 12,                   // 1-40
  "tone": "neutral",                   // neutral | warm | punchy | analytical
  "length": "standard",                // brief | standard | deep
  "good_news_mode": "balanced",        // balanced | uplifting | high_signal
  "enable_factcheck": true,
  "providers": []                      // [] = every configured provider
}
```

```json
{ "run_id": "8f14e45fceea167a5a36dedd4bea2543", "status": "created" }
```

### `GET /api/runs/{run_id}/stream`

Server-sent events. Four event types:

| Event | Payload |
|---|---|
| `node` | A `NodeEvent`: `{node, status, at, branch, detail, counts}` |
| `error` | `{message}` — a non-fatal problem; the run continues |
| `newsletter` | The complete `Newsletter` object |
| `done` | `{status}` — `done`, `partial`, `error`, or `not_found` |

`branch` identifies the parallel branch (a sub-topic id or an article id) for
fan-out nodes, and is `null` for single nodes.

```
event: node
data: {"node":"planner","status":"done","detail":"4 angles across 1 theme(s) via LLM",...}

event: node
data: {"node":"research","status":"done","branch":"a1b2c3","detail":"...8 articles via rss",...}

event: newsletter
data: {"title":"...","sections":[...],"sources":[...]}

event: done
data: {"status":"done"}
```

Disconnecting cancels the run and records it as `cancelled` — it will not be
left stuck at `running`.

### `GET /api/runs?limit=50&status=done`

Run history, newest first. `status` filters by `running`, `done`, `partial`,
`error`, or `cancelled`. `source` tells you what started it: `manual`, `query`,
or `schedule:{id}`.

### `GET /api/runs/{run_id}`

As above, plus the full `newsletter` object (or `null`).

### `DELETE /api/runs/{run_id}`

Deletes the run and its bookmarks. `404` if unknown.

### `GET /api/runs/{run_id}/export/{format}`

`format` is `markdown`, `html`, or `pdf`. Returns the file as an attachment.

- `409` — the run has no newsletter yet.
- `501` — PDF requested but WeasyPrint is not installed (`pip install weasyprint`).

---

## Briefing

### `POST /api/news/query`

Runs the pipeline and waits. Returns one structured answer.

```jsonc
{
  "topic": "coral reef restoration",   // required, 3-300 chars
  "section": null,                     // optional narrowing phrase
  "output_format": "briefing",         // briefing | newsletter | analysis | source_list
  "depth": 3,                          // 1-5 research angles
  "max_sources": 8,                    // 1-40
  "days": 14,                          // 1-365, how far back to look
  "include_citations": true,
  "good_news_mode": "balanced",
  "tone": "neutral",
  "providers": [],
  "enable_factcheck": true
}
```

```jsonc
{
  "result_id": "…", "run_id": "…", "topic": "coral reef restoration",
  "generated_at": "2026-08-27T10:31:00Z",
  "output_format": "briefing",
  "executive_summary": "…",
  "key_points": ["… (Reuters)", "… (Nature)"],
  "analysis": "## Recovery\n- Headline — Reuters, 2026-08-21\n  - A quoted claim",
  "sources": [
    { "title": "…", "url": "https://…", "source_type": "web",
      "publisher": "Reuters", "published_at": "2026-08-21T09:00:00Z",
      "relevance_score": 0.82, "summary": "…",
      "metadata": { "article_id": "…" } }
  ],
  "confidence": "medium",              // high | medium | low
  "suggested_followups": ["…"],
  "critic_notes": ["…"]
}
```

`confidence` is derived, not guessed: `high` needs ≥5 stories from ≥3 distinct
publishers with ≥5 verified facts; `medium` needs ≥3 stories from ≥2 publishers;
anything thinner, or any degraded run, is `low`.

`output_format: "source_list"` returns the citations with an empty `analysis`.

The request is bounded by `LLM_TIMEOUT_SECONDS × 12`; exceeding it returns `504`.
Use the streaming API for long runs.

---

## Bookmarks

### `POST /api/runs/{run_id}/bookmarks` → `201`

```json
{ "article_id": "abc123", "url": "https://reuters.com/story",
  "title": "A story", "source_name": "Reuters" }
```

Idempotent — saving the same `article_id` twice updates rather than duplicates.
`404` if the run is unknown.

### `GET /api/runs/{run_id}/bookmarks`
### `DELETE /api/runs/{run_id}/bookmarks/{article_id}`
### `GET /api/bookmarks?limit=200`

The last one is the reading list across every run.

---

## Schedules

Recurring newsletters. The server executes these itself; results appear in run
history with `source: "schedule:{id}"`.

### `POST /api/schedules` → `201`

```json
{
  "themes": ["ocean restoration", "coral reefs"],
  "cron_expr": "0 8 * * mon-fri",
  "config": { "theme": "ocean restoration", "max_sources": 8 }
}
```

`themes` overrides the config's theme: the first becomes `theme`, the rest
`extra_themes`. Everything else in `config` is preserved.

`cron_expr` is standard 5-field cron — `minute hour day-of-month month
day-of-week`, supporting `*`, `5`, `1,5,9`, `1-5`, `*/15`, `1-20/5`, month and
weekday names, and the `@hourly` / `@daily` / `@weekly` / `@monthly` aliases.
Invalid expressions are rejected at the edge with `422`.

The response includes `next_run_at`, the next firing time in UTC.

### `GET /api/schedules`
### `PATCH /api/schedules/{schedule_id}` — body `{"enabled": false}`
### `DELETE /api/schedules/{schedule_id}`
### `POST /api/schedules/{schedule_id}/run`

The last one fires a schedule immediately and returns the `run_id` it will write
to. Follow it with the SSE stream to watch it.

---

## Feedback

### `POST /api/news/feedback` → `201`

```json
{ "run_id": "…", "article_id": null, "rating": 4, "comment": "useful" }
```

`rating` is 1–5. `run_id` may be `null` for anonymous feedback; if given it must
exist. Returns `{"feedback_id": "…", "status": "recorded"}`.

### `GET /api/news/feedback?run_id=…&limit=100`

```json
{ "summary": { "count": 12, "average_rating": 4.2 }, "items": [ … ] }
```

---

## Health and introspection

### `GET /api/health`

Liveness. `{"status": "ok", "version": "0.3.0"}`.

### `GET /api/ready`

Readiness. **Always returns 200**, with `status` either `ready` or `degraded`,
and a per-dependency breakdown (`database`, `llm`, `search`, `scheduler`). This
is deliberate: the app stays usable on heuristic fallbacks when the LLM is down,
so failing the probe would pull a working service out of a load balancer for no
reason. Alert on the `status` field, not the HTTP code.

For Ollama the `llm` check reports whether the daemon is reachable *and* whether
the configured model is actually pulled.

### `GET /api/status`

Effective configuration — the providers a run will actually use, not merely
those available. `using_real_data` is `false` when only the mock is in play, and
the UI shows a banner accordingly.

### `GET /api/graph/topology`

Nodes and edges of the pipeline, for rendering the live progress view.
