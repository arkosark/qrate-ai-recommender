from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import date
from enum import Enum


class VisitContext(str, Enum):
    DATE_NIGHT = "Date Night"
    PRE_GAME = "Pre-Game"
    BUSINESS_LUNCH = "Business Lunch"
    RECOVERY = "Recovery"
    CASUAL = "Casual"
    CELEBRATION = "Celebration"
    FAMILY = "Family"


class PreferenceMap(BaseModel):
    spice_level: Optional[int] = Field(None, ge=1, le=5)
    likes_wine: Optional[bool] = None
    likes_beer: Optional[bool] = None
    likes_cocktails: Optional[bool] = None
    texture_prefs: list[str] = Field(default_factory=list)
    # e.g. ["crunchy", "creamy", "light"]
    flavor_prefs: list[str] = Field(default_factory=list)
    # e.g. ["citrus", "umami", "sweet"]
    drink_preference: Optional[str] = None
    # e.g. "margarita", "beer", "none"

    class Config:
        extra = "allow"  # allow restaurant-specific extensions


class GuestProfile(BaseModel):
    guest_id: Optional[UUID] = None
    # Hard constraints — drive Step 1 hard filter
    allergens: list[str] = Field(default_factory=list)
    # e.g. ["nuts", "shellfish", "dairy"]
    dietary_restrictions: list[str] = Field(default_factory=list)
    # e.g. ["vegetarian", "halal"]
    spice_preference: Optional[int] = Field(None, ge=1, le=5)
    favorite_cuisines: list[str] = Field(default_factory=list)
    # Soft signals — drive Step 2/3
    preference_map: PreferenceMap = Field(default_factory=PreferenceMap)
    context_history: Optional[str] = None
    anniversary_date: Optional[date] = None
    birthday: Optional[date] = None
    visit_context: Optional[VisitContext] = None

    @property
    def is_birthday_today(self) -> bool:
        if not self.birthday:
            return False
        from datetime import date as dt
        today = dt.today()
        return self.birthday.month == today.month and self.birthday.day == today.day

    @property
    def is_anniversary_today(self) -> bool:
        if not self.anniversary_date:
            return False
        from datetime import date as dt
        today = dt.today()
        return (
            self.anniversary_date.month == today.month
            and self.anniversary_date.day == today.day
        )

    class Config:
        from_attributes = True
