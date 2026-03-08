"""
Unit tests for Step 4 — Cross-Sell.
"""
import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.pipeline.step4_cross_sell import cross_sell
from app.models.guest import GuestProfile, PreferenceMap

ACCEPTED_ITEM_ID = UUID("a1b2c3d4-0001-0000-0000-000000000001")
CROSS_SELL_IDS = [UUID("a1b2c3d4-0020-0000-0000-000000000020")]

MOCK_DB_ROWS = [
    SimpleNamespace(
        id="a1b2c3d4-0020-0000-0000-000000000020",
        name="Skinny Margarita",
        description="Fresh lime, tequila",
        food_tags={"category": "cocktail,drink", "flavors": ["citrus"]},
        price=11.0,
        margin_score=9.0,
    )
]

CLAUDE_CROSS_SELL_RESPONSE = json.dumps({
    "selected_item_id": "a1b2c3d4-0020-0000-0000-000000000020",
    "selected_item_name": "Skinny Margarita",
    "pitch": "The bright citrus of a skinny margarita is the perfect match for your tacos!",
})


def _make_cross_sell_db() -> AsyncMock:
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = MOCK_DB_ROWS
    db.execute = AsyncMock(return_value=mock_result)
    return db


class TestCrossSell:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_pointers(self):
        guest = GuestProfile()
        db = AsyncMock()
        result = await cross_sell(db, ACCEPTED_ITEM_ID, [], guest)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_cross_sell_recommendation(self):
        guest = GuestProfile(preference_map=PreferenceMap(drink_preference="margarita"))
        db = _make_cross_sell_db()
        with patch("app.pipeline.step4_cross_sell.invoke_claude", return_value=CLAUDE_CROSS_SELL_RESPONSE):
            result = await cross_sell(db, ACCEPTED_ITEM_ID, CROSS_SELL_IDS, guest)
        assert result is not None
        assert result.item_name == "Skinny Margarita"
        assert "citrus" in result.pitch or "margarita" in result.pitch.lower()

    @pytest.mark.asyncio
    async def test_trigger_item_id_set_correctly(self):
        guest = GuestProfile()
        db = _make_cross_sell_db()
        with patch("app.pipeline.step4_cross_sell.invoke_claude", return_value=CLAUDE_CROSS_SELL_RESPONSE):
            result = await cross_sell(db, ACCEPTED_ITEM_ID, CROSS_SELL_IDS, guest)
        assert result.trigger_item_id == ACCEPTED_ITEM_ID

    @pytest.mark.asyncio
    async def test_returns_none_when_db_returns_empty(self):
        guest = GuestProfile()
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        result = await cross_sell(db, ACCEPTED_ITEM_ID, CROSS_SELL_IDS, guest)
        assert result is None

    @pytest.mark.asyncio
    async def test_drink_preference_filters_candidates(self):
        """Ensure drink preference narrows candidate list before calling Claude."""
        guest = GuestProfile(preference_map=PreferenceMap(drink_preference="margarita"))
        db = _make_cross_sell_db()
        with patch("app.pipeline.step4_cross_sell.invoke_claude", return_value=CLAUDE_CROSS_SELL_RESPONSE) as mock_claude:
            await cross_sell(db, ACCEPTED_ITEM_ID, CROSS_SELL_IDS, guest)
            # Verify Claude was called with margarita-relevant context
            call_args = mock_claude.call_args[0]
            assert "margarita" in call_args[1].lower()
