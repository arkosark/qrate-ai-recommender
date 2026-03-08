"""
Unit tests for Step 1 — Hard Filter.
Pure logic tests with a mocked DB — no infrastructure needed.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.pipeline.step1_hard_filter import hard_filter, _build_incompatible_tags
from app.models.guest import GuestProfile, PreferenceMap


RESTAURANT_ID = UUID("a0000000-0000-0000-0000-000000000001")
SAFE_IDS = [
    UUID("a1b2c3d4-0002-0000-0000-000000000002"),  # Avocado Salad (vegan, no allergens)
    UUID("a1b2c3d4-0008-0000-0000-000000000008"),  # Vegan Black Bean Burger
]


def _make_mock_db(row_ids: list[UUID]) -> AsyncMock:
    """Create a mock DB that returns the given UUIDs from execute."""
    db = AsyncMock()
    mock_rows = [MagicMock(id=str(rid)) for rid in row_ids]
    mock_result = MagicMock()
    mock_result.fetchall.return_value = mock_rows
    db.execute = AsyncMock(return_value=mock_result)
    return db


class TestBuildIncompatibleTags:
    def test_vegetarian_incompatible_with_meat(self):
        tags = _build_incompatible_tags(["vegetarian"])
        assert "meat" in tags
        assert "chicken" in tags

    def test_vegan_includes_dairy(self):
        tags = _build_incompatible_tags(["vegan"])
        assert "dairy" in tags
        assert "eggs" in tags
        assert "meat" in tags

    def test_halal_excludes_pork_and_alcohol(self):
        tags = _build_incompatible_tags(["halal"])
        assert "pork" in tags
        assert "alcohol" in tags

    def test_unknown_restriction_returns_empty(self):
        tags = _build_incompatible_tags(["unknown_restriction"])
        assert tags == []

    def test_multiple_restrictions_merged(self):
        tags = _build_incompatible_tags(["vegetarian", "halal"])
        assert "meat" in tags
        assert "pork" in tags
        assert "alcohol" in tags


class TestHardFilter:
    @pytest.mark.asyncio
    async def test_no_allergens_returns_all_items(self):
        guest = GuestProfile(allergens=[], dietary_restrictions=[])
        db = _make_mock_db(SAFE_IDS)
        result = await hard_filter(db, RESTAURANT_ID, guest)
        assert len(result) == 2
        assert all(isinstance(r, UUID) for r in result)

    @pytest.mark.asyncio
    async def test_nut_allergy_query_includes_allergen_clause(self):
        guest = GuestProfile(allergens=["nuts"], dietary_restrictions=[])
        db = _make_mock_db(SAFE_IDS)
        await hard_filter(db, RESTAURANT_ID, guest)
        # Verify execute was called and the query contains allergen logic
        call_args = db.execute.call_args
        query_str = str(call_args[0][0])
        assert "allergens" in query_str or "food_tags" in query_str

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self):
        guest = GuestProfile(allergens=["nuts", "shellfish", "dairy", "gluten"], dietary_restrictions=[])
        db = _make_mock_db([])
        result = await hard_filter(db, RESTAURANT_ID, guest)
        assert result == []

    @pytest.mark.asyncio
    async def test_vegan_dietary_restriction_applied(self):
        guest = GuestProfile(allergens=[], dietary_restrictions=["vegan"])
        db = _make_mock_db(SAFE_IDS)
        await hard_filter(db, RESTAURANT_ID, guest)
        call_args = db.execute.call_args
        query_str = str(call_args[0][0])
        assert "dietary" in query_str or "food_tags" in query_str

    @pytest.mark.asyncio
    async def test_returns_uuid_objects(self):
        some_id = UUID("a1b2c3d4-0002-0000-0000-000000000002")
        guest = GuestProfile(allergens=[], dietary_restrictions=[])
        db = _make_mock_db([some_id])
        result = await hard_filter(db, RESTAURANT_ID, guest)
        assert isinstance(result[0], UUID)
        assert result[0] == some_id
