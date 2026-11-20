"""Bounded public facility metadata reads from the approved VA sandbox only.

Facility metadata does not establish patient assignment or booking authority.
"""

import hashlib
import os
import re
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

BASE_URL = "https://sandbox-api.va.gov/services/va_facilities/v1"
_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_LIMIT = 32


def read_health_facility(facility_id: str, *, http=None) -> dict:
    if not isinstance(facility_id, str) or not re.fullmatch(
        r"vha_[A-Za-z0-9]{1,32}", facility_id
    ):
        raise ValueError("Explicit VA health facility ID required")
    if (
        os.getenv("VA_SANDBOX_ENABLED", "").lower() != "true"
        or os.getenv("VA_FACILITIES_READ_ENABLED", "").lower() != "true"
    ):
        raise PermissionError("VA facility reads are disabled")
    key = os.getenv("VA_FACILITIES_API_KEY", "").strip()
    if not key:
        raise PermissionError("VA Facilities credential is not configured")
    # Experimental, off by default. Only public facility metadata is eligible.
    # Credentials and enablement are checked on every call, including cache hits.
    ttl = int(os.getenv("VAB_FACILITY_METADATA_CACHE_SECONDS", "0"))
    if not 0 <= ttl <= 60:
        raise ValueError("Facility metadata cache TTL must be between 0 and 60")
    cache_key = (facility_id, hashlib.sha256(key.encode()).digest())
    now = time.monotonic()
    if ttl:
        with _CACHE_LOCK:
            entry = _CACHE.get(cache_key)
            if entry and 0 <= now - entry[0] < min(ttl, entry[1]):
                return {
                    **entry[2],
                    "cache_hit": True,
                    "cache_age_seconds": round(now - entry[0], 3),
                }
    result = _fetch_health_facility(facility_id, key=key, http=http)
    if ttl:
        with _CACHE_LOCK:
            if len(_CACHE) >= _CACHE_LIMIT:
                _CACHE.pop(next(iter(_CACHE)))
            _CACHE[cache_key] = (time.monotonic(), ttl, dict(result))
    return {**result, "cache_hit": False, "cache_age_seconds": 0.0}


def _fetch_health_facility(facility_id, *, key, http=None):
    owned = http is None
    client = http or httpx.Client(timeout=8, follow_redirects=False)
    try:
        response = client.get(
            f"{BASE_URL}/facilities/{facility_id}",
            headers={"apikey": key, "Accept": "application/json"},
            timeout=8,
            follow_redirects=False,
        )
        if response.status_code != 200:
            raise RuntimeError("VA facility lookup unavailable")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("VA facility response is malformed")
        data = payload.get("data")
        if not isinstance(data, dict) or data.get("id") != facility_id:
            raise ValueError("VA facility response does not match requested ID")
        attributes = data.get("attributes")
        if not isinstance(attributes, dict):
            raise ValueError("VA facility attributes missing")
        name, zone = attributes.get("name"), attributes.get("timeZone")
        if (
            not isinstance(name, str)
            or not 1 <= len(name.strip()) <= 120
            or any(ord(c) < 32 for c in name)
        ):
            raise ValueError("VA facility name invalid")
        try:
            if not isinstance(zone, str) or not zone:
                raise ValueError("VA facility time zone missing")
            ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("VA facility time zone invalid") from exc
        return {
            "facility_id": facility_id,
            "name": name,
            "time_zone": zone,
            "source": "VA_FACILITIES_API_SANDBOX",
            "source_verified": True,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "patient_assignment_verified": False,
            "booking_authority": False,
        }
    except httpx.HTTPError as exc:
        raise RuntimeError("VA facility lookup unavailable") from exc
    finally:
        if owned:
            client.close()
