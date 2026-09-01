"""Evidence-based platform posting windows in Infenergy's Central audience time."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

CENTRAL_TIME = ZoneInfo("America/Chicago")

# Monday is 0. Minutes avoid the competition spike at exactly :00.
FACEBOOK_TIMES = ("21:05", "08:05", "08:05", "09:05", "08:05", "22:05", "10:05")
INSTAGRAM_TIMES = ("19:05", "19:05", "12:05", "09:05", "22:05", "21:05", "21:05")
LINKEDIN_TIMES = ("22:05", "16:05", "16:05", "17:05", "15:05", "09:05", "22:05")

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