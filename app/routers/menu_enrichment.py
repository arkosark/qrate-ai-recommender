"""
POST /api/v1/menu/enrich-embeddings
Batch job: generate Titan embeddings for all menu items in a restaurant.
Protected — requires Cognito JWT with restaurant admin or service role.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.postgres import get_db
from app.services.embeddings import embed_menu_item, get_items_missing_embeddings
from app.middleware.auth import verify_cognito_token
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class EnrichRequest(BaseModel):
    restaurant_id: UUID
    limit: int = 500  # batch size per invocation


class EnrichResponse(BaseModel):
    restaurant_id: str
    queued: int
    message: str


async def _run_enrichment(db_session_factory, restaurant_id: UUID, limit: int) -> None:
    """Background task: embed all items missing vectors."""
    from app.services.postgres import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        items = await get_items_missing_embeddings(db, restaurant_id, limit)
        logger.info(
            "Starting batch embedding",
            restaurant_id=str(restaurant_id),
            item_count=len(items),
        )
        success = 0
        for item in items:
            try:
                await embed_menu_item(
                    db,
                    item_id=item["id"],
                    name=item["name"],
                    description=item.get("description", ""),
                    food_tags=item.get("food_tags", {}),
                )
                success += 1
            except Exception as exc:
                logger.error(
                    "Embedding failed for item",
                    item_id=str(item["id"]),
                    error=str(exc),
                )
        logger.info(
            "Batch embedding complete",
            restaurant_id=str(restaurant_id),
            success=success,
            total=len(items),
        )


@router.post("/menu/enrich-embeddings", response_model=EnrichResponse)
async def enrich_embeddings(
    request: EnrichRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(verify_cognito_token),
) -> EnrichResponse:
    """
    Kicks off background embedding generation for all menu items
    in the specified restaurant that don't have an embedding yet.
    """
    items = await get_items_missing_embeddings(db, request.restaurant_id, request.limit)

    if not items:
        return EnrichResponse(
            restaurant_id=str(request.restaurant_id),
            queued=0,
            message="All menu items already have embeddings",
        )

    from app.services.postgres import AsyncSessionLocal
    background_tasks.add_task(
        _run_enrichment, AsyncSessionLocal, request.restaurant_id, request.limit
    )

    logger.info(
        "Enrichment job queued",
        restaurant_id=str(request.restaurant_id),
        item_count=len(items),
    )

    return EnrichResponse(
        restaurant_id=str(request.restaurant_id),
        queued=len(items),
        message=f"Embedding generation queued for {len(items)} items",
    )
