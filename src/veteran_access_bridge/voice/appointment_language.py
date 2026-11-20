"""Patient-local appointment language and bounded spoken confirmation parsing."""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

ZONES = {
    "pacific": "America/Los_Angeles",
    "mountain": "America/Denver",
    "central": "America/Chicago",
    "eastern": "America/New_York",
    "arizona": "America/Phoenix",
    "hawaii": "Pacific/Honolulu",
    "alaska": "America/Anchorage",
}


def spoken_zone(text: str) -> str | None:
    words = set(re.findall(r"[a-z]+", text.lower()))
    if words & {"not", "no", "maybe", "unsure"}:
        return None
    matches = {zone for label, zone in ZONES.items() if label in words}
    return matches.pop() if len(matches) == 1 else None


def explicitly_confirms(text: str) -> bool:
    clean = " ".join(re.findall(r"[a-z]+", text.lower()))
    return clean in {
        "yes",
        "yeah",
        "yep",
        "yeah please",
        "yes please",
        "yes book it",
        "yes please book it",
        "yes book that appointment",
        "please book that appointment",
        "yes that is correct",
        "yes go ahead",
        "go ahead and book it",
    }


def local_appointment_time(value: datetime, zone: str) -> str:
    if value.tzinfo is None or zone not in set(ZONES.values()):
        raise ValueError("A confirmed supported patient time zone is required")
    local = value.astimezone(ZoneInfo(zone))
    hour = local.hour % 12 or 12
    minute = f":{local.minute:02d}" if local.minute else ""
    period = "AM" if local.hour < 12 else "PM"
    return (
        f"{local.strftime('%A, %B')} {local.day}, {local.year} "
        f"at {hour}{minute} {period} {local.tzname()}"
    )
