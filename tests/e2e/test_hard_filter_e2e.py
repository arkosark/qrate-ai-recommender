"""
E2E tests for Step 1 — Hard Filter against real local PostgreSQL.
Proves the safety guarantee: allergen items NEVER appear in safe set.
"""
import pytest
import pytest_asyncio
from uuid import UUID

from app.pipeline.step1_hard_filter import hard_filter
from app.models.guest import GuestProfile

RESTAURANT_ID = UUID("r0000000-0000-0000-0000-000000000001")
PEANUT_CHICKEN_ID = UUID("a1b2c3d4-0003-0000-0000-000000000003")
HABANERO_TACOS_ID = UUID("a1b2c3d4-0001-0000-0000-000000000001")  # contains shellfish


@pytest_asyncio.fixture
async def db():
    """Real DB session — requires docker-compose test stack running."""
    from app.services.postgres import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        yield session


class TestHardFilterE2E:
    @pytest.mark.asyncio
    async def test_nut_allergy_blacklist(self, db):
        """
        Core safety test: nut allergy guest must NEVER see Peanut Chicken Satay.
        """
        guest = GuestProfile(allergens=["nuts"], dietary_restrictions=[])
        safe_ids = await hard_filter(db, RESTAURANT_ID, guest)
        assert PEANUT_CHICKEN_ID not in safe_ids, (
            "SAFETY VIOLATION: Peanut item returned for nut-allergy guest!"
        )

    @pytest.mark.asyncio
    async def test_shellfish_allergy_blacklist(self, db):
        """Shellfish allergy guest must not see Habanero Shrimp Tacos."""
        guest = GuestProfile(allergens=["shellfish"], dietary_restrictions=[])
        safe_ids = await hard_filter(db, RESTAURANT_ID, guest)
        assert HABANERO_TACOS_ID not in safe_ids, (
            "SAFETY VIOLATION: Shellfish item returned for shellfish-allergy guest!"
        )

    @pytest.mark.asyncio
    async def test_no_allergens_returns_all_items_with_embeddings(self, db):
        """Guest with no restrictions should see all items that have embeddings."""
        guest = GuestProfile(allergens=[], dietary_restrictions=[])
        safe_ids = await hard_filter(db, RESTAURANT_ID, guest)
        assert len(safe_ids) > 0

    @pytest.mark.asyncio
    async def test_vegan_dietary_excludes_meat_items(self, db):
        """Vegan guest must not see items tagged with 'meat'."""
        guest = GuestProfile(allergens=[], dietary_restrictions=["vegan"])
        safe_ids = await hard_filter(db, RESTAURANT_ID, guest)
        # Peanut Chicken Satay is tagged 'meat' — should be excluded
        assert PEANUT_CHICKEN_ID not in safe_ids

    @pytest.mark.asyncio
    async def test_multi_allergen_guest(self, db):
        """Guest with nuts + shellfish + dairy should have fewer options."""
        guest_multi = GuestProfile(allergens=["nuts", "shellfish", "dairy"], dietary_restrictions=[])
        guest_none = GuestProfile(allergens=[], dietary_restrictions=[])

        safe_multi = await hard_filter(db, RESTAURANT_ID, guest_multi)
        safe_none = await hard_filter(db, RESTAURANT_ID, guest_none)

        # Multi-allergen guest should have equal or fewer safe items
        assert len(safe_multi) <= len(safe_none)

    @pytest.mark.asyncio
    async def test_extreme_allergen_guest_may_return_empty(self, db):
        """A guest with all possible allergens may have an empty safe set (not a crash)."""
        guest = GuestProfile(
            allergens=["nuts", "shellfish", "dairy", "gluten", "eggs", "soy", "fish", "sesame"],
            dietary_restrictions=["vegan"],
        )
        safe_ids = await hard_filter(db, RESTAURANT_ID, guest)
        assert isinstance(safe_ids, list)  # No exception, just empty list
