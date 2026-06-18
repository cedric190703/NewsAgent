# AI News Agent

AI News Agent is a planned multi-agent news intelligence platform that fetches, filters, analyzes, fact-checks, and formats information from web sources, RSS feeds, and internal knowledge resources. The goal is to let a user ask for news, analysis, or briefings about a topic and receive a professional, structured answer with sources, context, and actionable insights.

The first version will use a Python FastAPI backend, a React + Vite frontend, Docker-based deployment, and local LLM execution through Ollama. The architecture is designed so the model provider can later be extended to OpenRouter or other hosted/free model APIs.

## Workflow Schema

![AI Newsletter Agent workflow](./medias/Schema-workflow-AI.png)

## Product Vision

The system should behave like a professional AI news analyst:

- Understand the user's topic, section, intent, and expected output format.
- Retrieve information from multiple source types.
- Remove duplicate or low-value content.
- Score relevance and group related stories.
- Generate summaries, analysis, key insights, and recommendations.
- Review the generated answer for factual consistency, tone, and completeness.
- Deliver the answer through a web UI first, with future support for email newsletters, Slack, exports, and API consumers.
- Learn from user feedback to improve future responses.

## High-Level Architecture

```text
User request
    |
    v
React + Vite frontend
    |
    v
FastAPI backend
    |
    v
Orchestrator agent
    |
    +--> Web search agent
    +--> RSS/feed agent
    +--> RAG/knowledge-base agent
    |
    v
Content processor
    |
    +--> Deduplication
    +--> Relevance scoring
    +--> Topic clustering
    +--> Source normalization
    |
    v
Writer agent
    |
    v
Critic agent
    |
    v
Final response formatter
    |
    v
Web/chat UI, newsletter, API, Slack, or export
```

## Main Components

### Frontend

The frontend will be built with React and Vite. It should provide a clean professional interface where users can:

- Submit a topic, section, or question.
- Choose the expected output type: short answer, briefing, newsletter, analysis, or source list.
- Configure source preferences.
- View generated answers with source citations.
- Provide feedback on answer quality.

### Backend API

The backend will be built with Python and FastAPI. It will expose the application API, validate requests, manage agent execution, and return structured responses to the UI.

Expected responsibilities:

- Request validation and response formatting.
- Agent orchestration.
- Source ingestion.
- Content processing.
- LLM provider abstraction.
- Job status tracking for longer generation tasks.
- Storage integration for sources, generated answers, and feedback.

### Agent Pipeline

The agent pipeline is the core intelligence layer.

- **Orchestrator agent**: parses user intent, selects the right agents, and routes work.
- **Web search agent**: fetches current public web information.
- **RSS/feed agent**: collects content from configured feeds.
- **RAG/knowledge-base agent**: retrieves internal or saved reference material.
- **Content processor**: deduplicates, ranks, clusters, and normalizes retrieved content.
- **Writer agent**: produces summaries, analysis, key insights, and professional final drafts.
- **Critic agent**: reviews factual accuracy, tone, missing context, and answer quality.
- **Feedback loop**: captures user feedback for future improvements.

### AI Model Layer

The first implementation should use Ollama for local model inference.

The model layer should be implemented behind a provider interface so future providers can be added without rewriting the pipeline:

- Ollama for local development and privacy-friendly execution.
- OpenRouter as a future hosted multi-model gateway.
- Other free or low-cost model APIs if they fit the project requirements.

### Docker

Docker will be used to containerize the application and make local development reproducible.

The expected setup is:

- One backend container for FastAPI.
- One frontend container for React + Vite.
- Optional database/vector database containers.
- Optional Ollama container or connection to a host-running Ollama service.

## Proposed Repository Structure

```text
.
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── agents/
│   │   ├── core/
│   │   ├── models/
│   │   ├── providers/
│   │   ├── schemas/
│   │   └── services/
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   └── styles/
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
├── README.md
└── Schema-workflow-AI.png
```

## Initial API Direction

The first backend API can start small:

- `POST /api/news/query`: submit a user topic or question.
- `GET /api/news/jobs/{job_id}`: check long-running generation status.
- `GET /api/news/results/{result_id}`: retrieve a generated answer.
- `POST /api/feedback`: submit user feedback.
- `GET /api/health`: health check for Docker and deployment.

## Response Format Goal

Generated answers should be professional and structured. A typical response should include:

- Executive summary.
- Key points.
- Detailed analysis.
- Source list with links and timestamps when available.
- Confidence or quality notes.
- Suggested follow-up questions.

## Implementation Plan

### Phase 1: Project Foundation

- Create the backend FastAPI project.
- Create the frontend React + Vite project.
- Add Dockerfiles and `docker-compose.yml`.
- Add environment configuration for local development.
- Add a basic health check endpoint.

### Phase 2: Core AI Pipeline

- Implement the orchestrator agent.
- Add an Ollama provider abstraction.
- Define shared request and response schemas.
- Implement a first writer agent that can answer from provided context.
- Add a critic agent for answer review.

### Phase 3: Source Retrieval

- Add RSS/feed ingestion.
- Add web search integration.
- Add content extraction and normalization.
- Add deduplication and relevance scoring.
- Store source metadata for citations.

### Phase 4: RAG and Knowledge Base

- Add document ingestion.
- Add embeddings and vector search.
- Connect retrieved knowledge to the agent pipeline.
- Support local project resources as trusted context.

### Phase 5: Frontend Experience

- Build the query/chat interface.
- Display structured answers and citations.
- Add loading, error, and empty states.
- Add feedback controls.
- Add settings for model/source preferences.

### Phase 6: Delivery Channels

- Add newsletter generation.
- Add export formats.
- Add optional Slack/API delivery.
- Add scheduled briefings.

### Phase 7: Provider Expansion

- Add OpenRouter provider support.
- Add provider selection by environment variable.
- Add model fallback behavior.
- Add cost and rate-limit safeguards.

## Validation Needed

Before implementation, the main decisions to validate are:

- Which first source type should be implemented: RSS feeds, web search, or local knowledge base.
- Whether generated answers should be synchronous at first or use background jobs from the beginning.
- Which database should be used for stored results and feedback.
- Which vector store should be used for RAG.
- Whether Ollama should run inside Docker or separately on the host machine.
- Which output format should be the first priority: chat answer, newsletter, API response, or export.

## Local Development

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

To test the backend without a local Ollama model, set:

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
docker compose exec ollama ollama pull llama3.1
```

## Current Status

The project now contains a first runnable codebase:

- FastAPI backend with health, query, and feedback endpoints.
- Agent pipeline with orchestrator, configurable RSS, web, RAG, processor, writer, critic, and formatter layers.
- Ollama provider abstraction with a mock provider for local testing.
- React + Vite frontend for submitting news requests and reading structured results.
- Dockerfiles and `docker-compose.yml`.

The next implementation step is to replace placeholder web search and RAG agents with live integrations, then add persistence for generated results and feedback.
