from __future__ import annotations
 
import re
from datetime import date, datetime, time
 
from pydantic import BaseModel, Field, field_validator
 
 
VALID_KINDS = frozenset({
    "activity", "meal", "sightseeing", "snack",
    "breakfast", "brunch", "lunch", "dinner",
})

KIND_COERCION_MAP = {
    "restaurant": "meal",
    "food": "meal",
    "eat": "meal",
    "eating": "meal",
    "drink": "meal",
    "coffee": "snack",
    "bar": "meal",
    "walk": "activity",
    "walking": "activity",
    "transport": "activity",
    "travel": "activity",
    "museum": "sightseeing",
    "sight": "sightseeing",
    "visit": "sightseeing",
    "tour": "sightseeing",
    "shopping": "activity",
    "park": "activity",
    "beach": "activity",
    "nightlife": "activity",
    "evening": "dinner",
    "morning": "breakfast",
}
 
 
class TripParameters(BaseModel):
    city: str = Field(..., min_length=1)
    country_hint: str = ""
    start_date: date
    num_days: int = Field(..., ge=1, le=30)
    budget_amount: float = Field(..., ge=0)
    currency: str = "EUR"
    food_focused: bool = False
    timezone: str = "Europe/Madrid"
    locale_queries: str = "auto"
 
 
class PlaceRef(BaseModel):
    name: str = Field(..., min_length=1)
    category: str = ""
    rough_cost_hint: str = ""
    source_urls: list[str] = Field(default_factory=list)
 
 
class ScheduleBlock(BaseModel):
    start: str = Field(..., description="Local time HH:MM")
    end: str = Field(..., description="Local time HH:MM")
    title: str = Field(..., min_length=1)
    description: str = ""
    kind: str = "activity"
 
    @field_validator("start", "end")
    @classmethod
    def validate_hhmm(cls, value: str) -> str:
        text = value.strip()
        if not re.match(r"^\d{1,2}:\d{1,2}$", text):
            raise ValueError(f"Time must be HH:MM, got: {text!r}")
        hour, minute = int(text.split(":")[0]), int(text.split(":")[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"Invalid clock time: {text!r}")
        return f"{hour:02d}:{minute:02d}"
 
    @field_validator("kind", mode="before")
    @classmethod
    def coerce_kind(cls, value: object) -> str:
        text = str(value).strip().lower()
        if text in VALID_KINDS:
            return text
        if text in KIND_COERCION_MAP:
            return KIND_COERCION_MAP[text]
        for keyword, mapped in KIND_COERCION_MAP.items():
            if keyword in text:
                return mapped
        return "activity"
 
 
class DayPlan(BaseModel):
    date: str = Field(..., description="ISO date YYYY-MM-DD")
    blocks: list[ScheduleBlock] = Field(default_factory=list)
 
    @field_validator("date")
    @classmethod
    def validate_iso_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value
 
 
class ItineraryPlan(BaseModel):
    city: str = Field(..., min_length=1)
    country_hint: str = ""
    season: str = ""
    budget_notes: str = ""
    places: list[PlaceRef] = Field(default_factory=list)
    days: list[DayPlan] = Field(default_factory=list)
 
 
def parse_hhmm(s: str) -> time:
    parts = s.strip().split(":")
    return time(int(parts[0]), int(parts[1]))
 
 
def combine_local(day: date, t: time, tz_name: str) -> datetime:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        zi = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        from datetime import timezone
        zi = timezone.utc
    return datetime(day.year, day.month, day.day, t.hour, t.minute, tzinfo=zi)