from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class WeatherSignal(BaseModel):
    condition: str  # "sunny", "rainy", "cold", "hot"
    temperature_f: Optional[float] = None
    feels_like_f: Optional[float] = None
    description: Optional[str] = None


class LocalEvent(BaseModel):
    event_name: str
    event_type: str  # "sports", "concert", "festival"
    starts_at: Optional[datetime] = None
    venue: Optional[str] = None
    estimated_attendance: Optional[int] = None


class HolidayMeta(BaseModel):
    holiday_name: str  # "St. Patrick's Day", "Super Bowl Sunday"
    holiday_type: str  # "national", "sporting", "cultural"
    is_active: bool = True


class EnvironmentalContext(BaseModel):
    """
    Aggregated environmental signals injected at Step 3 (agentic reasoning).
    All fields are optional — the pipeline degrades gracefully if APIs are unavailable.
    """
    weather: Optional[WeatherSignal] = None
    local_events: list[LocalEvent] = Field(default_factory=list)
    active_holiday: Optional[HolidayMeta] = None
    timestamp: Optional[datetime] = None

    @property
    def summary(self) -> str:
        """Human-readable summary injected into Claude prompt."""
        parts = []
        if self.weather:
            parts.append(f"Weather: {self.weather.condition} ({self.weather.temperature_f}°F)")
        if self.active_holiday:
            parts.append(f"Holiday: {self.active_holiday.holiday_name}")
        if self.local_events:
            event_names = ", ".join(e.event_name for e in self.local_events[:2])
            parts.append(f"Local events: {event_names}")
        return "; ".join(parts) if parts else "No special environmental context"
