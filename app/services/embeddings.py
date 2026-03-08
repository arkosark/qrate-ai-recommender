"""
Embedding generation and storage for menu items.
Uses Amazon Titan Embeddings v2 via Bedrock (no new credentials needed).
"""
from uuid import UUID
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.services.bedrock import generate_embedding
from app.utils.logging import get_logger

logger = get_logger(__name__)


def build_menu_item_text(name: str, description: str, food_tags: dict) -> str:
    """
    Construct a rich text representation of a menu item for embedding.
    Includes name, description, and key flavor/dietary tags.
    """
    parts = [name]
    if description:
        parts.append(description)
    if food_tags:
        flavors = food_tags.get("flavors", [])
        cuisine = food_tags.get("cuisine", "")
        dietary = food_tags.get("dietary", [])
        if cuisine:
            parts.append(f"Cuisine: {cuisine}")
        if flavors:
            parts.append(f"Flavors: {', '.join(flavors)}")
        if dietary:
            parts.append(f"Dietary: {', '.join(dietary)}")
    return ". ".join(parts)


async def embed_menu_item(
    db: AsyncSession,
    item_id: UUID,
    name: str,
    description: str,
    food_tags: dict,
) -> list[float]:
    """
    Generate and persist embedding for a single menu item.
    Returns the embedding vector.
    """
    text_repr = build_menu_item_text(name, description or "", food_tags or {})
    logger.info("Generating embedding", item_id=str(item_id), text_preview=text_repr[:80])

    vector = generate_embedding(text_repr)

    # Store as pgvector — cast from Python list to vector type
    vector_str = "[" + ",".join(str(v) for v in vector) + "]"
    await db.execute(
        text(
            "UPDATE menu_items SET embedding_vector = :vec::vector WHERE id = :id"
        ),
        {"vec": vector_str, "id": str(item_id)},
    )
    await db.commit()
    logger.info("Embedding stored", item_id=str(item_id))
    return vector


async def get_items_missing_embeddings(
    db: AsyncSession, restaurant_id: UUID, limit: int = 500
) -> list[dict]:
    """Return menu items that have no embedding yet."""
    rows = await db.execute(
        text(
            """
            SELECT id, name, description, food_tags
            FROM menu_items
            WHERE restaurant_id = :rid
              AND embedding_vector IS NULL
            LIMIT :limit
            """
        ),
        {"rid": str(restaurant_id), "limit": limit},
    )
    return [
        {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "food_tags": row.food_tags or {},
        }
        for row in rows.fetchall()
    ]
