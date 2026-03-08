from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recommendation import RecommendRequest, RecommendResponse
from app.models.guest import GuestProfile, PreferenceMap, VisitContext
from app.pipeline.orchestrator import run_pipeline
from app.services.postgres import get_db
from app.services.environmental import build_environmental_context
from app.middleware.auth import optional_auth
from app.utils.logging import get_logger
from sqlalchemy import text

logger = get_logger(__name__)

router = APIRouter()


async def _load_guest_profile(
    db: AsyncSession,
    request: RecommendRequest,
    auth_claims: dict | None,
) -> GuestProfile:
    """
    If guest_id is provided, load profile from diner_profiles table.
    Otherwise, build an anonymous profile with defaults.
    """
    if request.guest_id is None:
        return GuestProfile(
            guest_id=None,
            visit_context=request.visit_context,
        )

    row = await db.execute(
        text(
            """
            SELECT
                id, dietary_restrictions, allergens, spice_preference,
                favorite_cuisines, preference_map, context_history,
                anniversary_date, birthday, visit_context
            FROM diner_profiles
            WHERE id = :guest_id
            """
        ),
        {"guest_id": str(request.guest_id)},
    )
    profile_row = row.fetchone()
    if not profile_row:
        logger.warning("Guest profile not found, using anonymous", guest_id=str(request.guest_id))
        return GuestProfile(guest_id=request.guest_id, visit_context=request.visit_context)

    pref_map_data = profile_row.preference_map or {}
    return GuestProfile(
        guest_id=request.guest_id,
        dietary_restrictions=profile_row.dietary_restrictions or [],
        allergens=profile_row.allergens or [],
        spice_preference=profile_row.spice_preference,
        favorite_cuisines=profile_row.favorite_cuisines or [],
        preference_map=PreferenceMap(**pref_map_data) if pref_map_data else PreferenceMap(),
        context_history=profile_row.context_history,
        anniversary_date=profile_row.anniversary_date,
        birthday=profile_row.birthday,
        visit_context=request.visit_context or (
            VisitContext(profile_row.visit_context) if profile_row.visit_context else None
        ),
    )


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(
    request: RecommendRequest,
    db: AsyncSession = Depends(get_db),
    auth_claims: dict | None = Depends(optional_auth),
) -> RecommendResponse:
    """
    Main recommendation endpoint.
    Runs the 4-step pipeline: hard filter → semantic search → Claude reasoning → cross-sell.
    Supports both authenticated (guest profile loaded) and anonymous guests.
    """
    logger.info(
        "Recommendation request",
        session_id=request.session_id,
        restaurant_id=str(request.restaurant_id),
        guest_id=str(request.guest_id) if request.guest_id else "anonymous",
        message_preview=request.message[:50],
    )

    try:
        guest = await _load_guest_profile(db, request, auth_claims)
        env_context = await build_environmental_context(
            override=request.environmental_override
        )
        response = await run_pipeline(
            db=db,
            session_id=request.session_id,
            restaurant_id=request.restaurant_id,
            guest=guest,
            message=request.message,
            cart_items=request.cart_items,
            env_context=env_context,
        )
        return response

    except ValueError as exc:
        logger.warning("Pipeline validation error", error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Pipeline error", error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Recommendation pipeline failed")
