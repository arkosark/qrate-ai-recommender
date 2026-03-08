"""
Step 2 — Semantic Search via pgvector
Converts guest message + preference_map → Titan embedding → cosine similarity search.
Returns top-N menu items most semantically aligned with guest intent.
"""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.models.guest import GuestProfile
from app.services.bedrock import generate_embedding
from app.utils.logging import get_logger

logger = get_logger(__name__)

TOP_N = 5


def _build_query_text(message: str, guest: GuestProfile) -> str:
    """
    Combine the guest's natural language message with their preference signals
    into a single rich text for embedding.
    """
    parts = [message]
    prefs = guest.preference_map
    if prefs.flavor_prefs:
        parts.append(f"Likes: {', '.join(prefs.flavor_prefs)}")
    if prefs.texture_prefs:
        parts.append(f"Texture preferences: {', '.join(prefs.texture_prefs)}")
    if guest.favorite_cuisines:
        parts.append(f"Favorite cuisines: {', '.join(guest.favorite_cuisines)}")
    if prefs.spice_level is not None:
        parts.append(f"Spice level: {prefs.spice_level}/5")
    if guest.visit_context:
        parts.append(f"Occasion: {guest.visit_context.value}")
    return ". ".join(parts)


async def semantic_search(
    db: AsyncSession,
    safe_item_ids: list[UUID],
    message: str,
    guest: GuestProfile,
    top_n: int = TOP_N,
) -> list[dict]:
    """
    Returns top_n items from safe_item_ids ordered by cosine similarity to guest query.

    Each result dict: { item_id, item_name, similarity_score, margin_score,
                        upsell_pointers, cross_sell_pointers, food_tags, price }
    """
    if not safe_item_ids:
        logger.warning("No safe items to search — skipping semantic search")
        return []

    query_text = _build_query_text(message, guest)
    logger.info("Generating query embedding", text_preview=query_text[:80])
    query_vector = generate_embedding(query_text)
    vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

    # pgvector cosine distance: <=>  (lower = more similar)
    # We pass safe IDs as a PostgreSQL array
    id_list = "{" + ",".join(str(i) for i in safe_item_ids) + "}"

    rows = await db.execute(
        text(
            """
            SELECT
                id,
                name,
                margin_score,
                upsell_pointers,
                cross_sell_pointers,
                food_tags,
                price,
                1 - (embedding_vector <=> :qvec::vector) AS similarity_score
            FROM menu_items
            WHERE id = ANY(:safe_ids::uuid[])
              AND embedding_vector IS NOT NULL
            ORDER BY embedding_vector <=> :qvec::vector
            LIMIT :top_n
            """
        ),
        {
            "qvec": vector_str,
            "safe_ids": id_list,
            "top_n": top_n,
        },
    )

    results = []
    for row in rows.fetchall():
        results.append(
            {
                "item_id": str(row.id),
                "item_name": row.name,
                "similarity_score": round(float(row.similarity_score), 4),
                "margin_score": float(row.margin_score or 5.0),
                "upsell_pointers": list(row.upsell_pointers or []),
                "cross_sell_pointers": list(row.cross_sell_pointers or []),
                "food_tags": row.food_tags or {},
                "price": float(row.price) if row.price else None,
            }
        )

    logger.info(
        "Semantic search complete",
        candidates=len(safe_item_ids),
        results=len(results),
        top_item=results[0]["item_name"] if results else "none",
    )
    return results
