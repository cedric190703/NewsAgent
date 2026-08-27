# Contributing

## Before you open a PR

```bash
make lint    # ruff + tsc, both must be clean
make test    # the backend suite must pass
```

CI runs the same checks on Python 3.11 and 3.12, plus a frontend build, a
pipeline smoke test, and a Docker image build.

## Ground rules

These are the conventions the codebase is built on. A change that breaks one of
them needs a reason in the PR description.

**Typed hand-offs.** Nothing crosses a node boundary as free text. If you need a
new field between stages, add it to the model in `app/graph/state.py`.

**Graceful degradation.** Any node that calls the model must have a
deterministic fallback and must record which one produced the output
(`summarized_by`, `scored_by`). A run degrades; it does not crash.

**No unverifiable output.** If you add something the newsletter shows a reader,
it must trace back to fetched content. Facts carry verbatim quotes that are
checked against the article body.

**Explicit request bodies.** A bare scalar in a FastAPI route signature becomes a
*query* parameter — the bug that made bookmarking impossible from the UI. Write
endpoints take a model from `app/api/schemas.py`.

**Fetch through `app.core.http`.** Never a bare `httpx` client. That module
applies the SSRF guard, the connection pool, and the global fetch budget.

**Layering.** Dependencies point downward: `api → services → graph → search →
core`. In particular `search` must never import from `graph`.

**Comments explain why.** The what is already in the code. Explain the
non-obvious constraint, the failure that motivated a guard, or the reason a
simpler approach does not work.

## Tests

Add tests next to the behaviour you change. Do not hit the network — use the
mock providers or a recorded payload. `tests/conftest.py` gives you a `client`
fixture running the app's real lifespan, an isolated `db`, and builders for
articles, summaries and newsletters.

If you are fixing a bug, add the test that would have caught it, and say in a
comment what it is guarding against.

## Adding a provider

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for search and LLM providers.
Both are Protocols; neither needs changes elsewhere in the pipeline.

## Commit messages

Present tense, imperative, and specific about the effect:

```
fix: bookmarks endpoint accepts a JSON body

Scalars in the route signature bound as query parameters, so every save
from the UI returned 422.
```
