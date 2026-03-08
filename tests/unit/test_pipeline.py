"""
Full pipeline unit tests — all external calls mocked.
Tests the orchestrator's step sequencing and priority hierarchy.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.pipeline.orchestrator import run_pipeline
from app.models.guest import GuestProfile, PreferenceMap, VisitContext
from app.models.environment import EnvironmentalContext

RESTAURANT_ID = UUID("a0000000-0000-0000-0000-000000000001")
SESSION_ID = "test-pipeline-session-001"

SAFE_IDS = [
    UUID("a1b2c3d4-0004-0000-0000-000000000004"),
    UUID("a1b2c3d4-0002-0000-0000-000000000002"),
]

SEMANTIC_RESULTS = [
    {
        "item_id": "a1b2c3d4-0004-0000-0000-000000000004",
        "item_name": "Truffle Mushroom Risotto",
        "similarity_score": 0.91,
        "margin_score": 9.2,
        "upsell_pointers": [],
        "cross_sell_pointers": ["a1b2c3d4-0022-0000-0000-000000000022"],
        "food_tags": {},
        "price": 22.0,
    }
]

REASONING_RESULT = {
    "selected_item_id": "a1b2c3d4-0004-0000-0000-000000000004",
    "selected_item_name": "Truffle Mushroom Risotto",
    "pitch": "Our award-winning risotto is the perfect choice tonight.",
    "upsell": None,
    "reasoning": "Best semantic match, highest margin.",
    "raw_response": "{}",
}


def _make_orchestrator_db() -> AsyncMock:
    db = AsyncMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 10
    db.execute = AsyncMock(return_value=count_result)
    db.commit = AsyncMock()
    return db


class TestOrchestratorPipeline:
    @pytest.mark.asyncio
    async def test_full_pipeline_success(self):
        guest = GuestProfile()
        env = EnvironmentalContext()
        db = _make_orchestrator_db()

        with patch("app.pipeline.orchestrator.hard_filter", return_value=SAFE_IDS) as mock_hf, \
             patch("app.pipeline.orchestrator.semantic_search", return_value=SEMANTIC_RESULTS) as mock_ss, \
             patch("app.pipeline.orchestrator.agentic_reasoning", return_value=REASONING_RESULT) as mock_ar, \
             patch("app.pipeline.orchestrator.cross_sell", return_value=None) as mock_cs, \
             patch("app.pipeline.orchestrator.put_session"):

            response = await run_pipeline(
                db=db,
                session_id=SESSION_ID,
                restaurant_id=RESTAURANT_ID,
                guest=guest,
                message="creamy pasta",
                cart_items=[],
                env_context=env,
            )

        assert response.session_id == SESSION_ID
        assert response.recommendation.item_name == "Truffle Mushroom Risotto"
        assert response.cross_sell is None
        assert response.pipeline_trace.after_hard_filter == len(SAFE_IDS)

        # Verify step order
        mock_hf.assert_called_once()
        mock_ss.assert_called_once()
        mock_ar.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_safe_ids_raises_value_error(self):
        guest = GuestProfile(allergens=["nuts", "shellfish", "dairy", "gluten", "eggs"])
        env = EnvironmentalContext()
        db = _make_orchestrator_db()

        with patch("app.pipeline.orchestrator.hard_filter", return_value=[]), \
             patch("app.pipeline.orchestrator.put_session"):
            with pytest.raises(ValueError, match="No safe menu items"):
                await run_pipeline(
                    db=db,
                    session_id=SESSION_ID,
                    restaurant_id=RESTAURANT_ID,
                    guest=guest,
                    message="anything",
                    cart_items=[],
                    env_context=env,
                )

    @pytest.mark.asyncio
    async def test_upsell_in_trace_when_triggered(self):
        from app.models.recommendation import UpsellRecommendation
        upsell = UpsellRecommendation(
            item_id=UUID("a1b2c3d4-0010-0000-0000-000000000010"),
            item_name="Premium Guac",
            pitch="Add our fresh guac!",
        )
        reasoning_with_upsell = {**REASONING_RESULT, "upsell": upsell}
        # Item has no cross_sell_pointers to avoid cross-sell step
        semantic_no_cross = [{**SEMANTIC_RESULTS[0], "cross_sell_pointers": []}]
        guest = GuestProfile()
        env = EnvironmentalContext()
        db = _make_orchestrator_db()

        with patch("app.pipeline.orchestrator.hard_filter", return_value=SAFE_IDS), \
             patch("app.pipeline.orchestrator.semantic_search", return_value=semantic_no_cross), \
             patch("app.pipeline.orchestrator.agentic_reasoning", return_value=reasoning_with_upsell), \
             patch("app.pipeline.orchestrator.put_session"):

            response = await run_pipeline(
                db=db,
                session_id=SESSION_ID,
                restaurant_id=RESTAURANT_ID,
                guest=guest,
                message="something good",
                cart_items=[],
                env_context=env,
            )

        assert response.pipeline_trace.upsell_triggered is True
        assert response.recommendation.upsell is not None

    @pytest.mark.asyncio
    async def test_session_persisted_to_dynamodb(self):
        guest = GuestProfile()
        env = EnvironmentalContext()
        db = _make_orchestrator_db()
        semantic_no_cross = [{**SEMANTIC_RESULTS[0], "cross_sell_pointers": []}]

        with patch("app.pipeline.orchestrator.hard_filter", return_value=SAFE_IDS), \
             patch("app.pipeline.orchestrator.semantic_search", return_value=semantic_no_cross), \
             patch("app.pipeline.orchestrator.agentic_reasoning", return_value=REASONING_RESULT), \
             patch("app.pipeline.orchestrator.put_session") as mock_put:

            await run_pipeline(
                db=db,
                session_id=SESSION_ID,
                restaurant_id=RESTAURANT_ID,
                guest=guest,
                message="pasta",
                cart_items=[],
                env_context=env,
            )

        mock_put.assert_called_once()
        call_kwargs = mock_put.call_args[1]
        assert call_kwargs["session_id"] == SESSION_ID
