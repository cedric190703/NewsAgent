from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.news import router as news_router
from app.api.runs import router as runs_router
from app.core.config import settings
from app.services.store import init_db


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="Multi-agent news intelligence API powered by LangGraph.",
)


@app.on_event("startup")
async def _startup() -> None:
    await init_db()


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(news_router, prefix="/api/news", tags=["news"])
app.include_router(runs_router, prefix="/api", tags=["runs"])
