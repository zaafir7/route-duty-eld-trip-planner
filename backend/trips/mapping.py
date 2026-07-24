"""Free OpenStreetMap geocoding, routing, and route-position helpers."""

from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import dataclass

import requests
from django.core.cache import cache

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
OSRM_BASE_URL = os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org")
NOMINATIM_MIN_INTERVAL_SECONDS = 1.05

US_STATE_ABBREVIATIONS = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
}


class MappingServiceError(RuntimeError):
    pass


@dataclass
class _RateLimiter:
    lock: threading.Lock
    last_request_at: float = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            wait_seconds = NOMINATIM_MIN_INTERVAL_SECONDS - (now - self.last_request_at)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            self.last_request_at = time.monotonic()


_NOMINATIM_LIMITER = _RateLimiter(threading.Lock())
_THREAD_LOCAL = threading.local()


def _session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        _THREAD_LOCAL.session = session
    return session


def _headers() -> dict:
    return {
        "User-Agent": os.environ.get(
            "NOMINATIM_USER_AGENT",
            "RouteDuty/1.0 (Django-React hiring assessment)",
        ),
        "Accept-Language": "en",
    }


def _cached_json(cache_key: str, url: str, params: dict, *, rate_limited: bool) -> dict | list:
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    if rate_limited:
        _NOMINATIM_LIMITER.wait()

    try:
        response = _session().get(url, params=params, headers=_headers(), timeout=25)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise MappingServiceError("The mapping service is temporarily unavailable.") from exc

    cache.set(cache_key, payload, timeout=60 * 60 * 24 * 30)
    return payload


def _short_location(address: dict, display_name: str = "") -> str:
    city = next(
        (
            address.get(key)
            for key in ("city", "town", "village", "municipality", "hamlet", "county")
            if address.get(key)
        ),
        "",
    )
    state = address.get("state", "")
    country_code = str(address.get("country_code", "")).upper()
    iso_state = address.get("ISO3166-2-lvl4", "")

    if country_code == "US":
        state_code = ""
        if isinstance(iso_state, str) and iso_state.startswith("US-"):
            state_code = iso_state.split("-", 1)[1]
        state_code = state_code or US_STATE_ABBREVIATIONS.get(state, state)
        if city and state_code:
            return f"{city}, {state_code}"
        return city or state_code or display_name

    if city and state:
        return f"{city}, {state}"
    if city and country_code:
        return f"{city}, {country_code}"
    return city or state or display_name


def geocode(place_name: str) -> dict | None:
    query = " ".join(place_name.split())
    payload = _cached_json(
        f"geocode:{query.casefold()}",
        NOMINATIM_SEARCH_URL,
        {
            "q": query,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
            "countrycodes": "us",
        },
        rate_limited=True,
    )
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        return None

    item = payload[0]
    try:
        latitude = float(item["lat"])
        longitude = float(item["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    address = item.get("address", {})
    display_name = item.get("display_name", query)
    return {
        "name": query,
        "display_name": display_name,
        "short_name": _short_location(address, display_name) or query,
        "lat": latitude,
        "lon": longitude,
    }


def reverse_geocode(lat: float, lon: float) -> str:
    cache_key = f"reverse:{round(lat, 4)}:{round(lon, 4)}"
    payload = _cached_json(
        cache_key,
        NOMINATIM_REVERSE_URL,
        {
            "lat": f"{lat:.6f}",
            "lon": f"{lon:.6f}",
            "format": "jsonv2",
            "zoom": 10,
            "addressdetails": 1,
        },
        rate_limited=True,
    )
    address = payload.get("address", {}) if isinstance(payload, dict) else {}
    display_name = payload.get("display_name", "") if isinstance(payload, dict) else ""
    return _short_location(address, display_name)


def _instruction_text(step: dict) -> str:
    maneuver = step.get("maneuver", {})
    maneuver_type = maneuver.get("type", "continue").replace("_", " ")
    modifier = maneuver.get("modifier", "").replace("_", " ")
    road = step.get("name") or "the roadway"
    exit_number = maneuver.get("exit")

    if maneuver_type == "depart":
        return f"Depart on {road}"
    if maneuver_type == "arrive":
        return "Arrive at destination"
    if maneuver_type in {"roundabout", "rotary"}:
        exit_text = f" and take exit {exit_number}" if exit_number else ""
        return f"Enter the roundabout{exit_text} onto {road}"
    if maneuver_type == "merge":
        return f"Merge {modifier} onto {road}".replace("  ", " ")
    if maneuver_type in {"on ramp", "off ramp"}:
        return f"Take the {maneuver_type} {modifier} toward {road}".replace("  ", " ")
    if maneuver_type in {"turn", "fork", "end of road", "new name", "continue"}:
        verb = "Continue" if maneuver_type in {"continue", "new name"} else maneuver_type.title()
        return f"{verb} {modifier} onto {road}".replace("  ", " ")
    return f"{maneuver_type.title()} {modifier} on {road}".replace("  ", " ")


def _simplify_steps(steps: list[dict], max_steps: int = 24) -> list[dict]:
    selected = []
    for step in steps:
        distance_miles = step.get("distance", 0.0) / 1609.344
        maneuver_type = step.get("maneuver", {}).get("type", "")
        if distance_miles < 0.4 and maneuver_type not in {"depart", "arrive", "roundabout", "rotary"}:
            continue
        selected.append(
            {
                "instruction": _instruction_text(step),
                "distance_miles": round(distance_miles, 1),
                "duration_minutes": round(step.get("duration", 0.0) / 60),
            }
        )

    if len(selected) <= max_steps:
        return selected

    # Keep the list readable while always preserving the final arrival step.
    return [*selected[: max_steps - 1], selected[-1]]


def route_between(points: list[dict]) -> dict | None:
    if len(points) < 2:
        raise MappingServiceError("At least two mapped locations are required.")
    try:
        coordinates = ";".join(f"{float(point['lon']):.6f},{float(point['lat']):.6f}" for point in points)
    except (KeyError, TypeError, ValueError) as exc:
        raise MappingServiceError("A mapped location contained invalid coordinates.") from exc
    cache_key = f"route:{coordinates}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"{OSRM_BASE_URL.rstrip('/')}/route/v1/driving/{coordinates}"
    try:
        response = _session().get(
            url,
            params={
                "overview": "full",
                "geometries": "geojson",
                "steps": "true",
                "alternatives": "false",
            },
            headers=_headers(),
            timeout=35,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise MappingServiceError("The routing service is temporarily unavailable.") from exc

    if data.get("code") != "Ok" or not data.get("routes"):
        return None

    try:
        route = data["routes"][0]
        route_legs = []
        for index, leg in enumerate(route.get("legs", [])):
            distance = float(leg["distance"])
            duration = float(leg["duration"])
            if not math.isfinite(distance) or not math.isfinite(duration) or distance < 0 or duration < 0:
                raise ValueError("invalid route leg distance or duration")
            route_legs.append(
                {
                    "index": index,
                    "from_name": points[index]["name"],
                    "to_name": points[index + 1]["name"],
                    "miles": distance / 1609.344,
                    "driving_hours": duration / 3600,
                    "map_duration_hours": duration / 3600,
                    "instructions": _simplify_steps(leg.get("steps", [])),
                }
            )

        route_distance = float(route["distance"])
        route_duration = float(route["duration"])
        if (
            not math.isfinite(route_distance)
            or not math.isfinite(route_duration)
            or route_distance < 0
            or route_duration < 0
        ):
            raise ValueError("invalid route distance or duration")
        geometry = route["geometry"]["coordinates"]
        if not isinstance(geometry, list) or not geometry:
            raise ValueError("missing route geometry")
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise MappingServiceError("The routing service returned an invalid route response.") from exc

    result = {
        "miles": route_distance / 1609.344,
        "driving_hours": route_duration / 3600,
        "map_duration_hours": route_duration / 3600,
        "geometry": geometry,
        "legs": route_legs,
    }
    cache.set(cache_key, result, timeout=60 * 60 * 24 * 7)
    return result


def _haversine_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = a
    lon2, lat2 = b
    radius_miles = 3958.7613
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius_miles * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


def interpolate_route_position(
    geometry: list[list[float]], route_miles: float, target_mile: float
) -> dict:
    if not geometry:
        return {"lat": 0.0, "lon": 0.0}
    if len(geometry) == 1 or route_miles <= 0:
        return {"lat": geometry[0][1], "lon": geometry[0][0]}

    segment_lengths = [
        _haversine_miles(tuple(geometry[index]), tuple(geometry[index + 1]))
        for index in range(len(geometry) - 1)
    ]
    polyline_miles = sum(segment_lengths)
    if polyline_miles <= 0:
        return {"lat": geometry[0][1], "lon": geometry[0][0]}

    scaled_target = min(max(target_mile / route_miles, 0.0), 1.0) * polyline_miles
    travelled = 0.0
    for index, segment_miles in enumerate(segment_lengths):
        if travelled + segment_miles >= scaled_target:
            fraction = 0.0 if segment_miles == 0 else (scaled_target - travelled) / segment_miles
            lon1, lat1 = geometry[index]
            lon2, lat2 = geometry[index + 1]
            return {
                "lat": lat1 + (lat2 - lat1) * fraction,
                "lon": lon1 + (lon2 - lon1) * fraction,
            }
        travelled += segment_miles

    lon, lat = geometry[-1]
    return {"lat": lat, "lon": lon}