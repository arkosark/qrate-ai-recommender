"""
Main 4-step pipeline orchestrator.

Priority hierarchy (enforced here):
  1. Safety    — hard filter never negotiable
  2. Intent    — semantic match to guest request
  3. Upsell    — premium suggestion if margin_score > threshold
  4. Cross-sell — complete the meal if cart has no drink
"""
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guest import GuestProfile
from app.models.environment import EnvironmentalContext
from app.models.recommendation import (
    RecommendResponse,
    RecommendationResult,
    PipelineTrace,
    CrossSellRecommendation,
)
from app.pipeline.step1_hard_filter import hard_filter
from app.pipeline.step2_semantic_search import semantic_search
from app.pipeline.step3_agentic_reasoning import agentic_reasoning
from app.pipeline.step4_cross_sell import cross_sell
from app.services.dynamodb import get_session, put_session
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Category tags that indicate a drink item — used to detect "no drink in cart"
_DRINK_TAGS = {"drink", "beverage", "cocktail", "wine", "beer", "soda", "juice", "water"}


def _cart_has_drink(cart_items_data: list[dict]) -> bool:
    for item in cart_items_data:
        tags = set(item.get("food_tags", {}).get("category", "").lower().split(","))
        if tags & _DRINK_TAGS:
            return True
    return False


async def run_pipeline(
    db: AsyncSession,
    session_id: str,
    restaurant_id: UUID,
    guest: GuestProfile,
    message: str,
    cart_items: list[UUID],
    env_context: EnvironmentalContext,
) -> RecommendResponse:
    trace = PipelineTrace(environmental_summary=env_context.summary)

    # ── Step 1: Hard Filter ──────────────────────────────────────────────────
    safe_ids = await hard_filter(db, restaurant_id, guest)
    # Count total menu items for trace
    from sqlalchemy import text
    total_row = await db.execute(
        text("SELECT COUNT(*) FROM menu_items WHERE restaurant_id = :rid"),
        {"rid": str(restaurant_id)},
    )
    trace.total_menu_items = total_row.scalar() or 0
    trace.after_hard_filter = len(safe_ids)

    if not safe_ids:
        raise ValueError(
            f"No safe menu items found for restaurant {restaurant_id} "
            f"with guest constraints {guest.allergens}"
        )

    # ── Step 2: Semantic Search ──────────────────────────────────────────────
    top_candidates = await semantic_search(db, safe_ids, message, guest)
    trace.semantic_top5 = [
        {
            "item_id": c["item_id"],
            "item_name": c["item_name"],
            "similarity_score": c["similarity_score"],
        }
        for c in top_candidates
    ]

    # ── Step 3: Agentic Reasoning (Claude) ───────────────────────────────────
    reasoning_result = await agentic_reasoning(top_candidates, guest, message, env_context)

    trace.winning_item_id = reasoning_result["selected_item_id"]
    winner = next(
        (c for c in top_candidates if c["item_id"] == reasoning_result["selected_item_id"]),
        top_candidates[0] if top_candidates else None,
    )
    trace.margin_score_winner = winner["margin_score"] if winner else None
    trace.upsell_triggered = reasoning_result.get("upsell") is not None

    # ── Step 4: Cross-sell (conditional) ────────────────────────────────────
    cross_sell_result: CrossSellRecommendation | None = None
    if winner and winner.get("cross_sell_pointers"):
        # Only cross-sell if cart has no drink
        cart_has_drink = False  # Simplified — in prod, fetch cart item food_tags
        if not cart_has_drink:
            cross_sell_result = await cross_sell(
                db,
                UUID(reasoning_result["selected_item_id"]),
                [UUID(str(p)) for p in winner["cross_sell_pointers"]],
                guest,
            )
            trace.cross_sell_triggered = cross_sell_result is not None

    # ── Persist session to DynamoDB ──────────────────────────────────────────
    put_session(
        session_id=session_id,
        restaurant_id=str(restaurant_id),
        guest_id=str(guest.guest_id) if guest.guest_id else None,
        pipeline_results={
            "selected_item_id": reasoning_result["selected_item_id"],
            "reasoning": reasoning_result.get("reasoning", ""),
        },
        accepted_items=[],
        cross_sell_state={
            "triggered": cross_sell_result is not None,
            "item_id": str(cross_sell_result.item_id) if cross_sell_result else None,
        },
    )

    recommendation = RecommendationResult(
        item_id=reasoning_result["selected_item_id"],
        item_name=reasoning_result["selected_item_name"],
        pitch=reasoning_result["pitch"],
        upsell=reasoning_result.get("upsell"),
    )

    logger.info(
        "Pipeline complete",
        session_id=session_id,
        recommended=reasoning_result["selected_item_name"],
        upsell=trace.upsell_triggered,
        cross_sell=trace.cross_sell_triggered,
    )

    return RecommendResponse(
        session_id=session_id,
        recommendation=recommendation,
        cross_sell=cross_sell_result,
        pipeline_trace=trace,
    )
