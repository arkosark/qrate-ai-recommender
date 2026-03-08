"""
Step 4 — Cross-Sell
Triggered when a guest accepts an item that has cross_sell_pointers.
Claude generates a pairing pitch (e.g. "try a skinny margarita with extra lime").
"""
import json
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.models.guest import GuestProfile
from app.models.recommendation import CrossSellRecommendation
from app.services.bedrock import invoke_claude
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def cross_sell(
    db: AsyncSession,
    accepted_item_id: UUID,
    cross_sell_pointers: list[UUID],
    guest: GuestProfile,
) -> CrossSellRecommendation | None:
    """
    Given a just-accepted item and its cross-sell pointer IDs,
    select the best pairing based on guest drink preference and generate a pitch.

    Returns None if no valid cross-sell exists or guest has no cart gap.
    """
    if not cross_sell_pointers:
        return None

    # Check if guest already has a drink in cart (avoid redundant upsell)
    # This check is done at the orchestrator level before calling this step

    # Fetch cross-sell candidate details
    id_list = "{" + ",".join(str(i) for i in cross_sell_pointers) + "}"
    rows = await db.execute(
        text(
            """
            SELECT id, name, description, food_tags, price, margin_score
            FROM menu_items
            WHERE id = ANY(:ids::uuid[])
            ORDER BY margin_score DESC
            LIMIT 3
            """
        ),
        {"ids": id_list},
    )
    candidates = [
        {
            "item_id": str(row.id),
            "item_name": row.name,
            "description": row.description or "",
            "food_tags": row.food_tags or {},
            "price": float(row.price) if row.price else None,
            "margin_score": float(row.margin_score or 5.0),
        }
        for row in rows.fetchall()
    ]

    if not candidates:
        return None

    # Filter by guest drink preference if specified
    drink_pref = (guest.preference_map.drink_preference or "").lower()
    if drink_pref and drink_pref != "none":
        preferred = [
            c for c in candidates
            if drink_pref in c["item_name"].lower()
            or drink_pref in str(c.get("food_tags", {})).lower()
        ]
        if preferred:
            candidates = preferred

    logger.info(
        "Invoking Claude for cross-sell pitch",
        accepted_item=str(accepted_item_id),
        cross_sell_candidates=len(candidates),
        drink_pref=drink_pref,
    )

    system_prompt = """You are a friendly restaurant server suggesting a perfect pairing.
Generate a warm, brief pairing pitch (1-2 sentences max). Output ONLY JSON."""

    user_prompt = f"""
The guest just ordered item {accepted_item_id}.
Guest drink preference: "{drink_pref or 'no preference'}"
Allergens to NEVER suggest: {guest.allergens}

Cross-sell candidates:
{json.dumps(candidates, indent=2)}

Select the best pairing and generate a pitch. Output ONLY:
{{
  "selected_item_id": "uuid",
  "selected_item_name": "string",
  "pitch": "1-2 sentence pairing suggestion"
}}
"""

    raw = invoke_claude(system_prompt, user_prompt, max_tokens=256)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
        result = json.loads(cleaned)

    logger.info(
        "Cross-sell complete",
        selected=result.get("selected_item_name"),
        pitch_preview=result.get("pitch", "")[:60],
    )

    return CrossSellRecommendation(
        item_id=result["selected_item_id"],
        item_name=result["selected_item_name"],
        pitch=result["pitch"],
        trigger_item_id=accepted_item_id,
    )
