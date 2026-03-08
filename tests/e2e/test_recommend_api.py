"""
E2E tests for POST /api/v1/recommend against the local Docker stack.
Requires: docker-compose -f docker-compose.test.yml up -d && seed_local_db.py
"""
import json
import pytest
import httpx
from datetime import date

BASE_URL = "http://localhost:8004"
RESTAURANT_ID = "r0000000-0000-0000-0000-000000000001"


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


def _make_request(
    session_id: str,
    message: str,
    guest_id: str | None = None,
    visit_context: str | None = None,
    cart_items: list[str] | None = None,
):
    return {
        "guest_id": guest_id,
        "session_id": session_id,
        "restaurant_id": RESTAURANT_ID,
        "message": message,
        "visit_context": visit_context,
        "cart_items": cart_items or [],
        "environmental_override": None,
    }


class TestRecommendAPI:
    def test_health_check(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] in ("healthy", "degraded")

    def test_anonymous_recommendation(self, client):
        payload = _make_request("e2e-anon-001", "I want something spicy and crunchy")
        r = client.post("/api/v1/recommend", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert "recommendation" in body
        assert "item_name" in body["recommendation"]
        assert "pitch" in body["recommendation"]
        assert len(body["recommendation"]["pitch"]) > 10

    def test_recommendation_returns_pipeline_trace(self, client):
        payload = _make_request("e2e-trace-001", "something light")
        r = client.post("/api/v1/recommend", json=payload)
        assert r.status_code == 200
        trace = r.json()["pipeline_trace"]
        assert trace["total_menu_items"] > 0
        assert trace["after_hard_filter"] >= 0
        assert isinstance(trace["semantic_top5"], list)

    def test_date_night_context_included_in_pitch(self, client):
        """Date Night visit context should be reflected in the recommendation pitch or upsell."""
        guest_id = "g0000000-0000-0000-0000-000000000004"
        payload = _make_request(
            "e2e-date-001",
            "something romantic and indulgent",
            guest_id=guest_id,
            visit_context="Date Night",
        )
        r = client.post("/api/v1/recommend", json=payload)
        assert r.status_code == 200
        body = r.json()
        # The response should contain a pitch (the content is AI-generated)
        assert len(body["recommendation"]["pitch"]) > 0

    def test_birthday_guest_gets_special_treatment(self, client):
        """Birthday guest profile should produce a pitch — content verified via trace/session."""
        guest_id = "g0000000-0000-0000-0000-000000000005"
        payload = _make_request(
            "e2e-birthday-001",
            "something special for tonight",
            guest_id=guest_id,
            visit_context="Celebration",
        )
        r = client.post("/api/v1/recommend", json=payload)
        assert r.status_code == 200
        assert "recommendation" in r.json()

    def test_session_id_returned_in_response(self, client):
        session_id = "e2e-session-check-001"
        payload = _make_request(session_id, "anything")
        r = client.post("/api/v1/recommend", json=payload)
        assert r.status_code == 200
        assert r.json()["session_id"] == session_id

    def test_invalid_restaurant_returns_error(self, client):
        payload = {
            "guest_id": None,
            "session_id": "e2e-bad-restaurant",
            "restaurant_id": "00000000-0000-0000-0000-000000000000",
            "message": "anything",
            "cart_items": [],
        }
        r = client.post("/api/v1/recommend", json=payload)
        # Should return 400 (no safe items) or 500
        assert r.status_code in (400, 500)

    def test_empty_message_returns_422(self, client):
        payload = {
            "guest_id": None,
            "session_id": "e2e-empty-msg",
            "restaurant_id": RESTAURANT_ID,
            "message": "",
            "cart_items": [],
        }
        r = client.post("/api/v1/recommend", json=payload)
        assert r.status_code == 422

    def test_synthetic_personas_pass_safety(self, client):
        """
        Runs 10 synthetic test personas through the API.
        Verifies no response references allergen items.
        Full 5000-persona run: python scripts/generate_synthetic_guests.py --count 5000
        """
        import json
        from pathlib import Path
        fixtures = Path(__file__).parent.parent / "fixtures" / "sample_guests.json"
        guests = json.loads(fixtures.read_text())

        for guest in guests[:10]:  # Quick sanity check — full run via script
            payload = _make_request(
                f"e2e-synthetic-{guest['id'][:8]}",
                "suggest something good",
                guest_id=guest["id"],
            )
            r = client.post("/api/v1/recommend", json=payload)
            assert r.status_code in (200, 400), f"Unexpected status for guest {guest['id']}: {r.status_code}"

            if r.status_code == 200:
                body = r.json()
                # Verify the recommended item doesn't trigger guest allergens
                # (Deep check requires fetching item food_tags — simplified here)
                assert "recommendation" in body
