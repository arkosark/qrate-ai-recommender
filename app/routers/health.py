from fastapi import APIRouter
from app.services.postgres import check_db_health

router = APIRouter()


@router.get("/health")
async def health_check():
    db_ok = await check_db_health()
    return {
        "status": "healthy" if db_ok else "degraded",
        "service": "qrate-ai-recommender",
        "database": "ok" if db_ok else "unavailable",
    }
