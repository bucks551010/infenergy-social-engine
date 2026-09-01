"""Evidence-based platform posting windows in Infenergy's Central audience time."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

CENTRAL_TIME = ZoneInfo("America/Chicago")

# Monday is 0. Minutes avoid the competition spike at exactly :00.
FACEBOOK_TIMES = ("09:05", "09:05", "09:05", "09:05", "09:05", "08:05", "08:05")
INSTAGRAM_TIMES = ("18:05", "17:05", "17:05", "16:05", "16:05", "11:05", "13:05")
LINKEDIN_TIMES = ("11:05", "08:05", "16:05", "16:05", "16:05", "16:05", "16:05")

PLATFORM_TIMES = {
    "facebook": FACEBOOK_TIMES,
    "instagram": INSTAGRAM_TIMES,
    "linkedin": LINKEDIN_TIMES,
}


def growth_schedule(content_date: str | date) -> dict[str, str]:
    day = date.fromisoformat(content_date) if isinstance(content_date, str) else content_date
    result: dict[str, str] = {}
    for platform, weekly_times in PLATFORM_TIMES.items():
        hour, minute = (int(part) for part in weekly_times[day.weekday()].split(":"))
        result[platform] = datetime.combine(day, time(hour, minute), CENTRAL_TIME).isoformat()
    return result


def first_scheduled_at(content_date: str | date) -> str:
    return min(growth_schedule(content_date).values(), key=datetime.fromisoformat)