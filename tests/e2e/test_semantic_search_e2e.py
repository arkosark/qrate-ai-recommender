"""
E2E tests for Step 2 — Semantic Search against real pgvector.
Requires: local stack running + embeddings generated for test menu items.
"""
import pytest
import pytest_asyncio
from uuid import UUID

from app.pipeline.step2_semantic_search import semantic_search
from app.models.guest import GuestProfile, PreferenceMap

RESTAURANT_ID = UUID("r0000000-0000-0000-0000-000000000001")
CITRUS_SALMON_ID = UUID("a1b2c3d4-0006-0000-0000-000000000006")
HABANERO_TACOS_ID = UUID("a1b2c3d4-0001-0000-0000-000000000001")
AVOCADO_SALAD_ID = UUID("a1b2c3d4-0002-0000-0000-000000000002")

ALL_ITEM_IDS = [
    UUID("a1b2c3d4-0001-0000-0000-000000000001"),
    UUID("a1b2c3d4-0002-0000-0000-000000000002"),
    UUID("a1b2c3d4-0004-0000-0000-000000000004"),
    UUID("a1b2c3d4-0005-0000-0000-000000000005"),
    UUID("a1b2c3d4-0006-0000-0000-000000000006"),
    UUID("a1b2c3d4-0007-0000-0000-000000000007"),
    UUID("a1b2c3d4-0008-0000-0000-000000000008"),
]


@pytest_asyncio.fixture
async def db():
    from app.services.postgres import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        yield session


class TestSemanticSearchE2E:
    @pytest.mark.asyncio
    async def test_citrus_query_returns_citrus_dishes(self, db):
        """
        'Light citrus dish' should return citrus-tagged items (Citrus Salmon, Avocado Salad)
        in the top 3 results.
        """
        guest = GuestProfile(preference_map=PreferenceMap(flavor_prefs=["citrus", "light"]))
        results = await semantic_search(db, ALL_ITEM_IDS, "light citrus dish", guest)

        assert len(results) > 0
        top_ids = [UUID(r["item_id"]) for r in results[:3]]
        citrus_items = {CITRUS_SALMON_ID, AVOCADO_SALAD_ID}
        assert len(citrus_items & set(top_ids)) > 0, (
            f"Expected citrus items in top 3, got: {[r['item_name'] for r in results[:3]]}"
        )

    @pytest.mark.asyncio
    async def test_spicy_crunchy_query(self, db):
        """'Spicy and crunchy' should favor Habanero Tacos or Nashville Hot Chicken."""
        guest = GuestProfile(preference_map=PreferenceMap(flavor_prefs=["spicy", "crunchy"]))
        results = await semantic_search(db, ALL_ITEM_IDS, "spicy and crunchy", guest)

        assert len(results) > 0
        top_names = [r["item_name"] for r in results[:2]]
        assert any("Habanero" in n or "Nashville" in n for n in top_names), (
            f"Expected spicy/crunchy item in top 2, got: {top_names}"
        )

    @pytest.mark.asyncio
    async def test_similarity_scores_ordered_descending(self, db):
        """Results should be ordered by similarity score (highest first)."""
        guest = GuestProfile()
        results = await semantic_search(db, ALL_ITEM_IDS, "something delicious", guest)
        scores = [r["similarity_score"] for r in results]
        assert scores == sorted(scores, reverse=True), "Results not ordered by similarity"

    @pytest.mark.asyncio
    async def test_top_5_limit_respected(self, db):
        """Should never return more than 5 results by default."""
        guest = GuestProfile()
        results = await semantic_search(db, ALL_ITEM_IDS, "anything", guest, top_n=5)
        assert len(results) <= 5

    @pytest.mark.asyncio
    async def test_safe_ids_filter_enforced(self, db):
        """Only items in the safe_ids list should appear in results."""
        safe_subset = [AVOCADO_SALAD_ID]
        guest = GuestProfile()
        results = await semantic_search(db, safe_subset, "salad", guest)
        for r in results:
            assert UUID(r["item_id"]) in safe_subset, (
                f"Item {r['item_id']} not in safe_ids but appeared in results"
            )
