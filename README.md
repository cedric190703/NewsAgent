# Good News Agent

A multi-agent news intelligence platform that fetches, filters, scores, fact-checks, and assembles personalized newsletters from web sources and RSS feeds. Built with a Python FastAPI backend, React + Vite frontend, LangGraph orchestration, and local LLM execution via Ollama.

## Workflow Schema

![AI Newsletter Agent workflow](./medias/Schema-workflow-AI.png)

## Features

### Newsletter Generation Pipeline

- **Planner**: Breaks a theme into diverse research angles (breakthroughs, policy, market, research, applications, risks, community impact) using LLM or heuristic fallback
- **Research**: Parallel fan-out per sub-topic, fetching from RSS feeds, Tavily, NewsAPI, and custom URLs
- **Curator**: Scores articles on relevance, recency, credibility, valence (constructive outcomes), and signal (journalistic quality). Blends heuristic + LLM scoring (50/50 for relevance). Cross-subtopic deduplication and source diversity caps
- **Summarizer**: Parallel per-article summarization with quote-verified key facts
- **Fact-checker**: Cross-checks claims and flags conflicts between articles
- **Composer**: Assembles the final newsletter with LLM-written titles, intros, and section blurbs

### User Registration & Groups

- Multi-step registration flow: Welcome → Details → Profile (multi-select questionnaire) → Review → Done
- Users select multiple interests per question and are assigned to matching groups
- Review step shows all selected options and groups before final confirmation
- Admin can create/delete questions and options via the Admin Dashboard
- Each option maps to a group name; users can join multiple groups

### Newsletter Delivery

- One combined email per subscriber with content from all their groups, sequentially organized with group labels and dividers
- Subscribers in a single group receive the standard newsletter
- Subscribers in multiple groups receive a combined email with all group newsletters
- Email delivery via Resend API or SMTP fallback

### Admin Dashboard

- Pipeline orchestration: trigger newsletter generation runs with configurable themes, audiences, tones, lengths, and curation modes
- Subscriber management
- Question & option management (CRUD for registration questionnaire)
- Run history with newsletter previews
- Protected by admin key authentication

### User Portal

- Sign-in modal for returning users
- Registration modal with multi-select checkboxes and review step
- Newsletter browsing with search and filtering
- Preview/teaser content for non-authenticated visitors
- Dark mode support

## Architecture

```text
User/Admin (React + Vite)
    |
    v
FastAPI backend
    |
    v
LangGraph pipeline
    |
    +--> Planner (theme -> search angles)
    +--> Research (parallel, per angle)
    +--> Curator (score, rank, select)
    |       +--> widen_queries (retry on thin results)
    +--> Summarizer (parallel, per article)
    +--> Fact-checker (cross-reference claims)
    +--> Composer (assemble newsletter)
    |
    v
SQLite storage (runs, subscribers, groups, questions)
    |
    v
Email delivery (Resend / SMTP)
```

## Scoring System

Articles are scored on five independent axes:

| Axis | Description | Weight (Balanced) |
|------|-------------|-------------------|
| **Relevance** | Theme-specificity with synonym expansion, title/headline/body keyword density, tangential penalties | 0.38 |
| **Recency** | Exponential decay with 7-day half-life | 0.12 |
| **Credibility** | Tiered source reputation (TIER_ONE/TIER_TWO), domain trust markers, HTTPS, content length | 0.15 |
| **Valence** | Constructive outcome detection (positive vs. negative term lexicon) | 0.17 |
| **Signal** | Substantive journalism indicators (data, quotes, methodology) vs. hype/clickbait penalties | 0.18 |

Three curation modes adjust the weights:
- **Balanced**: Default, all axes considered
- **Uplifting**: Higher valence weight for constructive/positive news
- **High Signal**: Higher signal and credibility weight, valence excluded

## Tech Stack

- **Backend**: Python, FastAPI, LangGraph, Pydantic, SQLite (aiosqlite)
- **Frontend**: React, Vite, TypeScript, Tailwind CSS, Framer Motion, Lucide icons
- **LLM**: Ollama (local) with mock provider fallback
- **Search**: Tavily API, NewsAPI, RSS feeds (Google News, BBC, Guardian, NYT, Nature, Science, etc.)
- **Email**: Resend API or SMTP
- **Deployment**: Docker Compose

## Local Development

### Prerequisites

- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.ai) (for local LLM inference)
- Docker and Docker Compose (optional, for containerized deployment)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

To test without a local Ollama model:

```bash
LLM_PROVIDER=mock
```

To enable live RSS retrieval, add feed URLs to `backend/.env`:

```bash
RSS_FEEDS=["https://example.com/feed.xml"]
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

The UI will be available at `http://localhost:5173`.

### Docker Compose

```bash
docker compose up --build
```

This starts:

- FastAPI backend on `http://localhost:8000`
- React + Vite frontend on `http://localhost:5173`
- Ollama on `http://localhost:11434`

After the Ollama container starts, pull a model before using the default provider:

```bash
docker compose exec ollama ollama pull mistral:latest
```

## Configuration

Key environment variables (see `backend/.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | LLM provider (`ollama` or `mock`) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `mistral:latest` | Model name |
| `SEARCH_PROVIDERS` | `["auto"]` | Search providers to use |
| `TAVILY_API_KEY` | — | Tavily search API key |
| `NEWSAPI_KEY` | — | NewsAPI key |
| `RESEND_API_KEY` | — | Resend email API key |
| `SMTP_HOST` | — | SMTP server host (fallback for email) |
| `ADMIN_PASSWORD` | `admin123` | Admin dashboard password |
| `RELEVANCE_THRESHOLD` | `0.30` | Minimum relevance score for article selection |
| `RESULTS_PER_SUBTOPIC` | `20` | Max results to fetch per sub-topic |
| `MAX_SEARCH_ATTEMPTS` | `2` | Retry attempts when results are thin |

## API Endpoints

### Public

- `GET /api/health` — Health check
- `POST /api/runs` — Start a newsletter generation run
- `GET /api/runs` — List recent runs
- `GET /api/runs/{run_id}` — Get run status and newsletter
- `GET /api/newsletters` — List completed newsletters
- `GET /api/questions` — List registration questions
- `POST /api/register` — Register a subscriber with questionnaire answers
- `GET /api/subscriber/newsletters?email=...` — List newsletters for a subscriber

### Admin (requires `X-Admin-Key` header)

- `POST /api/questions` — Create a question with options
- `DELETE /api/questions/{question_id}` — Delete a question
- `GET /api/subscribers` — List subscribers
- `GET /api/groups` — List groups
- `POST /api/runs/{run_id}/send` — Send newsletter to subscribers
- `GET /api/runs/{run_id}/deliveries` — Check delivery status

## Repository Structure

```text
.
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routes
│   │   ├── core/          # Config and settings
│   │   ├── graph/         # LangGraph pipeline (nodes, scoring, state)
│   │   ├── providers/     # LLM provider abstraction
│   │   ├── search/        # Search provider integrations
│   │   └── services/      # Storage, mailer, exporter
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/    # React components (UserView, AdminView, modals)
│   │   ├── services/      # API client
│   │   ├── lib/           # Utilities
│   │   └── styles/        # CSS
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
├── README.md
└── medias/
```
