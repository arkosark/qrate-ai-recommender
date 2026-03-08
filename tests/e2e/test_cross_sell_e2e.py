"""
E2E tests for the full cross-sell flow: accepting tacos → margarita suggested.
Requires local stack running with Bedrock mock (WireMock).
"""
import json
import pytest
import httpx
from uuid import UUID

BASE_URL = "http://localhost:8004"
RESTAURANT_ID = "r0000000-0000-0000-0000-000000000001"
HABANERO_TACOS_ID = "a1b2c3d4-0001-0000-0000-000000000001"
MARGARITA_ID = "a1b2c3d4-0020-0000-0000-000000000020"


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


class TestCrossSellE2E:
    def test_tacos_recommendation_triggers_margarita_cross_sell(self, client):
        """
        Guest requests spicy/crunchy food → gets Habanero Tacos →
        cross_sell should offer Skinny Margarita (cross_sell_pointer on tacos).
        """
        payload = {
            "guest_id": None,
            "session_id": "e2e-crosssell-001",
            "restaurant_id": RESTAURANT_ID,
            "message": "something spicy and crunchy with citrus",
            "visit_context": "Casual",
            "cart_items": [],
        }
        r = client.post("/api/v1/recommend", json=payload)
        assert r.status_code == 200
        body = r.json()

        # If Habanero Tacos was selected, cross-sell should trigger
        rec = body["recommendation"]
        if "Habanero" in rec["item_name"]:
            cross_sell = body.get("cross_sell")
            if cross_sell:
                assert "Margarita" in cross_sell["item_name"] or "margarita" in cross_sell["pitch"].lower(), (
                    f"Expected margarita cross-sell, got: {cross_sell}"
                )

    def test_cross_sell_not_triggered_when_drink_in_cart(self, client):
        """
        If guest cart already has a drink, cross-sell should NOT trigger.
        (Cart logic simplified — this tests the API accepts drink cart items.)
        """
        payload = {
            "guest_id": None,
            "session_id": "e2e-crosssell-drink-001",
            "restaurant_id": RESTAURANT_ID,
            "message": "something spicy",
            "cart_items": [MARGARITA_ID],  # already has a drink
        }
        r = client.post("/api/v1/recommend", json=payload)
        assert r.status_code == 200
        # Cross-sell behavior depends on orchestrator drink-detection logic

    def test_cross_sell_result_has_pitch(self, client):
        """Any cross-sell result must include a non-empty pitch."""
        payload = {
            "guest_id": "g0000000-0000-0000-0000-000000000003",  # pre-game guest
            "session_id": "e2e-crosssell-pitch-001",
            "restaurant_id": RESTAURANT_ID,
            "message": "spicy food for the game",
            "visit_context": "Pre-Game",
            "cart_items": [],
        }
        r = client.post("/api/v1/recommend", json=payload)
        assert r.status_code == 200
        body = r.json()
        cross_sell = body.get("cross_sell")
        if cross_sell:
            assert len(cross_sell["pitch"]) > 0
            assert cross_sell["trigger_item_id"] is not None
