"""
Unit tests for Step 2 — Semantic Search.
Uses mocked pgvector responses and mocked Bedrock embedding generation.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.pipeline.step2_semantic_search import semantic_search, _build_query_text
from app.models.guest import GuestProfile, PreferenceMap, VisitContext

SAFE_IDS = [
    UUID("a1b2c3d4-0001-0000-0000-000000000001"),
    UUID("a1b2c3d4-0002-0000-0000-000000000002"),
    UUID("a1b2c3d4-0005-0000-0000-000000000005"),
]

MOCK_EMBEDDING = [0.1] * 1536


def _make_semantic_mock_db(items: list[dict]) -> AsyncMock:
    db = AsyncMock()
    mock_rows = []
    for item in items:
        row = MagicMock()
        row.id = item["id"]
        row.name = item["name"]
        row.margin_score = item.get("margin_score", 5.0)
        row.upsell_pointers = item.get("upsell_pointers", [])
        row.cross_sell_pointers = item.get("cross_sell_pointers", [])
        row.food_tags = item.get("food_tags", {})
        row.price = item.get("price")
        row.similarity_score = item.get("similarity_score", 0.85)
        mock_rows.append(row)
    mock_result = MagicMock()
    mock_result.fetchall.return_value = mock_rows
    db.execute = AsyncMock(return_value=mock_result)
    return db


class TestBuildQueryText:
    def test_message_always_included(self):
        guest = GuestProfile()
        text = _build_query_text("spicy and crunchy", guest)
        assert "spicy and crunchy" in text

    def test_flavor_prefs_included(self):
        guest = GuestProfile(preference_map=PreferenceMap(flavor_prefs=["citrus", "umami"]))
        text = _build_query_text("something fresh", guest)
        assert "citrus" in text
        assert "umami" in text

    def test_visit_context_included(self):
        guest = GuestProfile(visit_context=VisitContext.DATE_NIGHT)
        text = _build_query_text("romantic dinner", guest)
        assert "Date Night" in text

    def test_spice_level_included(self):
        guest = GuestProfile(preference_map=PreferenceMap(spice_level=5))
        text = _build_query_text("hot food", guest)
        assert "5/5" in text or "5" in text


class TestSemanticSearch:
    @pytest.mark.asyncio
    async def test_returns_top_n_results(self):
        items = [
            {"id": str(SAFE_IDS[0]), "name": "Tacos", "similarity_score": 0.92},
            {"id": str(SAFE_IDS[1]), "name": "Salad", "similarity_score": 0.85},
        ]
        guest = GuestProfile()
        with patch("app.pipeline.step2_semantic_search.generate_embedding", return_value=MOCK_EMBEDDING):
            db = _make_semantic_mock_db(items)
            result = await semantic_search(db, SAFE_IDS, "spicy", guest)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_safe_ids_returns_empty(self):
        guest = GuestProfile()
        db = AsyncMock()
        with patch("app.pipeline.step2_semantic_search.generate_embedding", return_value=MOCK_EMBEDDING):
            result = await semantic_search(db, [], "anything", guest)
        assert result == []
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_result_has_required_fields(self):
        items = [
            {
                "id": str(SAFE_IDS[0]),
                "name": "Habanero Tacos",
                "similarity_score": 0.91,
                "margin_score": 8.5,
                "upsell_pointers": [],
                "cross_sell_pointers": [],
                "food_tags": {"flavors": ["spicy"]},
                "price": 16.99,
            }
        ]
        guest = GuestProfile()
        with patch("app.pipeline.step2_semantic_search.generate_embedding", return_value=MOCK_EMBEDDING):
            db = _make_semantic_mock_db(items)
            result = await semantic_search(db, SAFE_IDS, "spicy", guest)
        assert result[0]["item_id"] == str(SAFE_IDS[0])
        assert result[0]["item_name"] == "Habanero Tacos"
        assert "similarity_score" in result[0]
        assert "margin_score" in result[0]
