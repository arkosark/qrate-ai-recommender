"""
Step 3 — Agentic Reasoning via Claude (AWS Bedrock)

Re-ranks top candidates by margin_score, checks upsell pointers,
injects environmental context (birthday, local event, weather, holiday),
and generates a personalized pitch in the restaurant's voice.
"""
import json
from app.models.guest import GuestProfile
from app.models.environment import EnvironmentalContext
from app.models.recommendation import UpsellRecommendation
from app.services.bedrock import invoke_claude
from app.utils.logging import get_logger

logger = get_logger(__name__)

UPSELL_MARGIN_THRESHOLD = 7.0


def _build_system_prompt() -> str:
    return """You are an expert AI dining concierge for a high-end restaurant platform.
Your job is to select the best menu item for a guest and craft a personalized,
compelling recommendation pitch that feels warm, knowledgeable, and on-brand.

Rules:
1. SAFETY FIRST — never recommend items with allergens matching guest restrictions
2. Match the guest's explicit request as closely as possible
3. Prefer higher-margin items when semantic similarity is close (within 0.05)
4. Use environmental context (occasion, weather, local events) to personalize the pitch
5. Keep pitches under 3 sentences — warm, specific, action-oriented
6. Output ONLY valid JSON — no markdown, no extra text"""


def _build_user_prompt(
    candidates: list[dict],
    guest: GuestProfile,
    message: str,
    env_context: EnvironmentalContext,
) -> str:
    occasion_signals = []
    if guest.is_birthday_today:
        occasion_signals.append("TODAY IS THE GUEST'S BIRTHDAY — make it special!")
    if guest.is_anniversary_today:
        occasion_signals.append("TODAY IS THE GUEST'S ANNIVERSARY — romantic touch!")
    if guest.visit_context:
        occasion_signals.append(f"Visit context: {guest.visit_context.value}")

    return f"""
Guest request: "{message}"

Guest profile:
- Allergens: {guest.allergens}
- Dietary restrictions: {guest.dietary_restrictions}
- Spice preference: {guest.spice_preference}/5
- Flavor preferences: {guest.preference_map.flavor_prefs}
- Texture preferences: {guest.preference_map.texture_prefs}
- Occasion signals: {occasion_signals}

Environmental context: {env_context.summary}

Top candidate menu items (already filtered for safety):
{json.dumps(candidates, indent=2)}

Task:
1. Select the BEST item for this guest from the candidates list
2. If the winner's upsell_pointers list is non-empty AND its margin_score > {UPSELL_MARGIN_THRESHOLD},
   select the first upsell pointer item_id for an upsell recommendation
3. Generate a warm, personalized pitch for the main item (max 3 sentences)
4. If upsell triggered, generate a brief upsell pitch (max 2 sentences)

Respond with ONLY this JSON structure:
{{
  "selected_item_id": "uuid",
  "selected_item_name": "string",
  "pitch": "string",
  "upsell_triggered": true/false,
  "upsell_item_id": "uuid or null",
  "upsell_pitch": "string or null",
  "reasoning": "1-2 sentences on why this item was chosen"
}}
"""


async def agentic_reasoning(
    candidates: list[dict],
    guest: GuestProfile,
    message: str,
    env_context: EnvironmentalContext,
) -> dict:
    """
    Returns a dict with: selected_item_id, selected_item_name, pitch,
    upsell_triggered, upsell_item_id, upsell_pitch, reasoning
    """
    if not candidates:
        raise ValueError("No candidates provided to agentic reasoning step")

    # Pre-sort by margin_score to bias Claude toward high-margin items
    sorted_candidates = sorted(candidates, key=lambda x: x["margin_score"], reverse=True)

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(sorted_candidates, guest, message, env_context)

    logger.info(
        "Invoking Claude for recommendation reasoning",
        candidate_count=len(candidates),
        has_birthday=guest.is_birthday_today,
        env_summary=env_context.summary[:50],
    )

    raw_response = invoke_claude(system_prompt, user_prompt, max_tokens=512)

    try:
        result = json.loads(raw_response)
    except json.JSONDecodeError:
        # Claude occasionally adds markdown fences — strip and retry
        cleaned = raw_response.strip().removeprefix("```json").removesuffix("```").strip()
        result = json.loads(cleaned)

    logger.info(
        "Claude reasoning complete",
        selected=result.get("selected_item_name"),
        upsell_triggered=result.get("upsell_triggered"),
        reasoning=result.get("reasoning", "")[:80],
    )

    # Build structured upsell if triggered
    upsell = None
    if result.get("upsell_triggered") and result.get("upsell_item_id"):
        upsell = UpsellRecommendation(
            item_id=result["upsell_item_id"],
            item_name=result.get("upsell_item_name", "Premium Add-on"),
            pitch=result.get("upsell_pitch", ""),
        )

    return {
        "selected_item_id": result["selected_item_id"],
        "selected_item_name": result["selected_item_name"],
        "pitch": result["pitch"],
        "upsell": upsell,
        "reasoning": result.get("reasoning", ""),
        "raw_response": raw_response,
    }
