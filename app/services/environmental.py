"""
Environmental context signals: weather (OpenWeatherMap) + local events (PredictHQ).
Degrades gracefully — returns empty context if APIs are unavailable or keys missing.
"""
import httpx
from datetime import datetime
from app.models.environment import EnvironmentalContext, WeatherSignal, LocalEvent, HolidayMeta
from app.utils.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

WEATHER_API_URL = "https://api.openweathermap.org/data/2.5/weather"
PREDICTHQ_API_URL = "https://api.predicthq.com/v1/events/"

# Hardcoded holiday detection (extend as needed)
_HOLIDAY_MAP = {
    (3, 17): HolidayMeta(holiday_name="St. Patrick's Day", holiday_type="cultural"),
    (2, 2): HolidayMeta(holiday_name="Super Bowl Sunday", holiday_type="sporting"),
    (12, 25): HolidayMeta(holiday_name="Christmas", holiday_type="national"),
    (11, 27): HolidayMeta(holiday_name="Thanksgiving", holiday_type="national"),
    (7, 4): HolidayMeta(holiday_name="Independence Day", holiday_type="national"),
    (10, 31): HolidayMeta(holiday_name="Halloween", holiday_type="cultural"),
    (2, 14): HolidayMeta(holiday_name="Valentine's Day", holiday_type="cultural"),
}


def _detect_active_holiday(dt: datetime) -> HolidayMeta | None:
    return _HOLIDAY_MAP.get((dt.month, dt.day))


async def get_weather(lat: float, lon: float) -> WeatherSignal | None:
    if not settings.weather_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                WEATHER_API_URL,
                params={
                    "lat": lat,
                    "lon": lon,
                    "appid": settings.weather_api_key,
                    "units": "imperial",
                },
            )
            r.raise_for_status()
            data = r.json()
            return WeatherSignal(
                condition=data["weather"][0]["main"].lower(),
                temperature_f=data["main"]["temp"],
                feels_like_f=data["main"]["feels_like"],
                description=data["weather"][0]["description"],
            )
    except Exception as exc:
        logger.warning("Weather API failed", error=str(exc))
        return None


async def get_local_events(lat: float, lon: float, radius_km: int = 5) -> list[LocalEvent]:
    if not settings.predicthq_api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                PREDICTHQ_API_URL,
                headers={"Authorization": f"Bearer {settings.predicthq_api_key}"},
                params={
                    "within": f"{radius_km}km@{lat},{lon}",
                    "active.gte": datetime.utcnow().strftime("%Y-%m-%d"),
                    "limit": 5,
                    "sort": "phq_attendance",
                },
            )
            r.raise_for_status()
            results = r.json().get("results", [])
            return [
                LocalEvent(
                    event_name=e.get("title", "Local Event"),
                    event_type=e.get("category", "general"),
                    venue=e.get("venue", {}).get("name") if e.get("venue") else None,
                    estimated_attendance=e.get("phq_attendance"),
                )
                for e in results
            ]
    except Exception as exc:
        logger.warning("PredictHQ API failed", error=str(exc))
        return []


async def build_environmental_context(
    lat: float | None = None,
    lon: float | None = None,
    override: EnvironmentalContext | None = None,
) -> EnvironmentalContext:
    """
    Build full environmental context.
    If override is provided, returns it directly (test / manual injection).
    """
    if override is not None:
        return override

    now = datetime.utcnow()
    weather = None
    events = []

    if lat is not None and lon is not None:
        weather, events = await __import__("asyncio").gather(
            get_weather(lat, lon),
            get_local_events(lat, lon),
        )

    return EnvironmentalContext(
        weather=weather,
        local_events=events,
        active_holiday=_detect_active_holiday(now),
        timestamp=now,
    )
