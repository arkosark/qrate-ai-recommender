from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health, recommend, menu_enrichment
from app.utils.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="QRate AI Recommender",
    description="Semantic AI recommendation microservice for QRate dining platform",
    version="1.0.0",
    docs_url="/docs" if settings.environment != "prod" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten per environment via ALB/API Gateway
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(recommend.router, prefix="/api/v1")
app.include_router(menu_enrichment.router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
    logger.info("qrate-ai-recommender starting", environment=settings.environment, port=settings.port)


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("qrate-ai-recommender shutting down")
