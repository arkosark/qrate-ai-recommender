"""
Unit tests for Step 3 — Agentic Reasoning.
All Bedrock/Claude calls are mocked.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from uuid import UUID
from datetime import date

from app.pipeline.step3_agentic_reasoning import agentic_reasoning, _build_system_prompt, _build_user_prompt
from app.models.guest import GuestProfile, PreferenceMap, VisitContext
from app.models.environment import EnvironmentalContext, WeatherSignal, HolidayMeta

CANDIDATES = [
    {
        "item_id": "a1b2c3d4-0004-0000-0000-000000000004",
        "item_name": "Truffle Mushroom Risotto",
        "similarity_score": 0.88,
        "margin_score": 9.2,
        "upsell_pointers": ["a1b2c3d4-0011-0000-0000-000000000011"],
        "cross_sell_pointers": [],
        "food_tags": {"flavors": ["umami", "creamy"]},
        "price": 22.0,
    },
    {
        "item_id": "a1b2c3d4-0002-0000-0000-000000000002",
        "item_name": "Grilled Avocado Salad",
        "similarity_score": 0.75,
        "margin_score": 7.0,
        "upsell_pointers": [],
        "cross_sell_pointers": [],
        "food_tags": {"flavors": ["citrus", "light"]},
        "price": 13.5,
    },
]

CLAUDE_RESPONSE_NO_UPSELL = json.dumps({
    "selected_item_id": "a1b2c3d4-0004-0000-0000-000000000004",
    "selected_item_name": "Truffle Mushroom Risotto",
    "pitch": "This rich, earthy risotto is perfect for a special evening.",
    "upsell_triggered": False,
    "upsell_item_id": None,
    "upsell_pitch": None,
    "reasoning": "Highest margin item matching guest's umami preference.",
})

CLAUDE_RESPONSE_WITH_UPSELL = json.dumps({
    "selected_item_id": "a1b2c3d4-0004-0000-0000-000000000004",
    "selected_item_name": "Truffle Mushroom Risotto",
    "pitch": "Our truffle risotto is a Date Night staple — pure indulgence.",
    "upsell_triggered": True,
    "upsell_item_id": "a1b2c3d4-0011-0000-0000-000000000011",
    "upsell_item_name": "Shaved Truffle Add-on",
    "upsell_pitch": "Elevate it further with freshly shaved truffle — truly unforgettable.",
    "reasoning": "High margin, date night context, upsell available.",
})


class TestSystemPrompt:
    def test_contains_safety_first_rule(self):
        prompt = _build_system_prompt()
        assert "SAFETY FIRST" in prompt or "safety" in prompt.lower()

    def test_output_json_instruction(self):
        prompt = _build_system_prompt()
        assert "JSON" in prompt


class TestUserPrompt:
    def test_contains_guest_message(self):
        guest = GuestProfile()
        env = EnvironmentalContext()
        prompt = _build_user_prompt(CANDIDATES, guest, "something creamy", env)
        assert "something creamy" in prompt

    def test_birthday_signal_injected(self):
        guest = GuestProfile(birthday=date.today())
        env = EnvironmentalContext()
        prompt = _build_user_prompt(CANDIDATES, guest, "dinner", env)
        assert "BIRTHDAY" in prompt or "birthday" in prompt.lower()

    def test_environmental_summary_injected(self):
        env = EnvironmentalContext(
            active_holiday=HolidayMeta(holiday_name="St. Patrick's Day", holiday_type="cultural")
        )
        guest = GuestProfile()
        prompt = _build_user_prompt(CANDIDATES, guest, "dinner", env)
        assert "Patrick" in prompt


class TestAgenticReasoning:
    @pytest.mark.asyncio
    async def test_selects_item_no_upsell(self):
        guest = GuestProfile()
        env = EnvironmentalContext()
        with patch("app.pipeline.step3_agentic_reasoning.invoke_claude", return_value=CLAUDE_RESPONSE_NO_UPSELL):
            result = await agentic_reasoning(CANDIDATES, guest, "creamy pasta", env)
        assert result["selected_item_id"] == "a1b2c3d4-0004-0000-0000-000000000004"
        assert result["upsell"] is None

    @pytest.mark.asyncio
    async def test_upsell_returned_when_triggered(self):
        guest = GuestProfile(visit_context=VisitContext.DATE_NIGHT)
        env = EnvironmentalContext()
        with patch("app.pipeline.step3_agentic_reasoning.invoke_claude", return_value=CLAUDE_RESPONSE_WITH_UPSELL):
            result = await agentic_reasoning(CANDIDATES, guest, "umami dish", env)
        assert result["upsell"] is not None
        assert result["upsell"].item_id == UUID("a1b2c3d4-0011-0000-0000-000000000011")

    @pytest.mark.asyncio
    async def test_raises_on_empty_candidates(self):
        guest = GuestProfile()
        env = EnvironmentalContext()
        with pytest.raises(ValueError, match="No candidates"):
            await agentic_reasoning([], guest, "anything", env)

    @pytest.mark.asyncio
    async def test_handles_markdown_fenced_response(self):
        fenced = "```json\n" + CLAUDE_RESPONSE_NO_UPSELL + "\n```"
        guest = GuestProfile()
        env = EnvironmentalContext()
        with patch("app.pipeline.step3_agentic_reasoning.invoke_claude", return_value=fenced):
            result = await agentic_reasoning(CANDIDATES, guest, "pasta", env)
        assert "selected_item_id" in result

    @pytest.mark.asyncio
    async def test_pitch_always_returned(self):
        guest = GuestProfile()
        env = EnvironmentalContext()
        with patch("app.pipeline.step3_agentic_reasoning.invoke_claude", return_value=CLAUDE_RESPONSE_NO_UPSELL):
            result = await agentic_reasoning(CANDIDATES, guest, "pasta", env)
        assert len(result["pitch"]) > 0
