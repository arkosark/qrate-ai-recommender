from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID

from app.models.guest import VisitContext
from app.models.environment import EnvironmentalContext


class RecommendRequest(BaseModel):
    guest_id: Optional[UUID] = None
    session_id: str
    restaurant_id: UUID
    message: str = Field(..., min_length=1, max_length=500)
    visit_context: Optional[VisitContext] = None
    cart_items: list[UUID] = Field(default_factory=list)
    environmental_override: Optional[EnvironmentalContext] = None
    # If provided, skips live API calls and uses this context directly


class UpsellRecommendation(BaseModel):
    item_id: UUID
    item_name: str
    pitch: str


class CrossSellRecommendation(BaseModel):
    item_id: UUID
    item_name: str
    pitch: str
    trigger_item_id: UUID  # which accepted item triggered this


class PipelineTrace(BaseModel):
    total_menu_items: int = 0
    after_hard_filter: int = 0
    semantic_top5: list[dict] = Field(default_factory=list)
    # [{"item_id": "...", "item_name": "...", "similarity_score": 0.92}]
    winning_item_id: Optional[str] = None
    margin_score_winner: Optional[float] = None
    environmental_summary: str = ""
    upsell_triggered: bool = False
    cross_sell_triggered: bool = False


class RecommendationResult(BaseModel):
    item_id: UUID
    item_name: str
    pitch: str
    upsell: Optional[UpsellRecommendation] = None


class RecommendResponse(BaseModel):
    session_id: str
    recommendation: RecommendationResult
    cross_sell: Optional[CrossSellRecommendation] = None
    pipeline_trace: PipelineTrace
