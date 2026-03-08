"""
Step 1 — Hard Filter
Removes menu items that conflict with guest allergens or dietary restrictions.
This is a pure SQL operation — no AI involved. Safety is non-negotiable.

Priority 1 in agent hierarchy: Safety always blocks everything else.
"""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.models.guest import GuestProfile
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def hard_filter(
    db: AsyncSession,
    restaurant_id: UUID,
    guest: GuestProfile,
) -> list[UUID]:
    """
    Returns IDs of menu items that are SAFE for this guest.

    Logic:
    - Exclude items whose food_tags->'allergens' overlap with guest.allergens
    - Exclude items that violate guest.dietary_restrictions
      (e.g. guest is vegetarian → exclude items tagged 'meat')

    Uses PostgreSQL JSONB operators for efficiency.
    """
    allergens = guest.allergens or []
    dietary = guest.dietary_restrictions or []

    # Build allergen exclusion clause
    # food_tags->'allergens' is a JSONB array like ["nuts", "dairy"]
    allergen_clause = ""
    if allergens:
        # ?| operator: does the JSONB array contain ANY of these keys?
        # We store allergens as a JSONB array of strings
        allergen_clause = (
            "AND NOT (food_tags->'allergens' ?| ARRAY["
            + ", ".join(f"'{a}'" for a in allergens)
            + "])"
        )

    # Build dietary restriction clause
    # Dietary restriction logic: guest is vegetarian → exclude items tagged 'meat'/'chicken' etc.
    # We rely on the 'dietary' field in food_tags for positive labels
    dietary_clause = ""
    if dietary:
        # Items must not be incompatible with ANY of guest's restrictions
        # Incompatibility map — expand as needed
        incompatible = _build_incompatible_tags(dietary)
        if incompatible:
            dietary_clause = (
                "AND NOT (food_tags->'dietary' ?| ARRAY["
                + ", ".join(f"'{t}'" for t in incompatible)
                + "])"
            )

    query = f"""
        SELECT id FROM menu_items
        WHERE restaurant_id = :restaurant_id
          AND embedding_vector IS NOT NULL
          {allergen_clause}
          {dietary_clause}
    """
    rows = await db.execute(text(query), {"restaurant_id": str(restaurant_id)})
    safe_ids = [UUID(str(row.id)) for row in rows.fetchall()]

    logger.info(
        "Hard filter complete",
        restaurant_id=str(restaurant_id),
        allergens=allergens,
        dietary=dietary,
        safe_count=len(safe_ids),
    )
    return safe_ids


def _build_incompatible_tags(dietary_restrictions: list[str]) -> list[str]:
    """
    Maps guest dietary restrictions to food_tags that would make an item incompatible.
    E.g. if guest is vegetarian, items tagged 'meat' or 'chicken' are incompatible.
    """
    incompatible = set()
    restriction_map = {
        "vegetarian": ["meat", "chicken", "beef", "pork", "lamb", "seafood"],
        "vegan": ["meat", "chicken", "beef", "pork", "lamb", "seafood", "dairy", "eggs"],
        "halal": ["pork", "alcohol"],
        "kosher": ["pork", "shellfish"],
        "gluten_free": ["gluten"],
    }
    for restriction in dietary_restrictions:
        incompatible.update(restriction_map.get(restriction.lower(), []))
    return list(incompatible)
