from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .hos_calculator import DRIVING, build_trip_plan, split_segments_by_day, validate_plan
from .mapping import (
    MappingServiceError,
    geocode,
    interpolate_route_position,
    reverse_geocode,
    route_between,
)
from .serializers import TripRequestSerializer


def _offset_label(offset_seconds: int) -> str:
    sign = "+" if offset_seconds >= 0 else "-"
    absolute = abs(offset_seconds)
    hours, remainder = divmod(absolute, 3600)
    minutes = remainder // 60
    return f"{sign}{hours:02d}:{minutes:02d}"


def _resolve_time_basis(start_time_local: str, zone_name: str) -> tuple[datetime, timezone, dict]:
    zone = ZoneInfo(zone_name)
    if start_time_local:
        naive = datetime.fromisoformat(start_time_local)
        local_start = naive.replace(tzinfo=zone)
    else:
        local_start = datetime.now(zone).replace(second=0, microsecond=0)

    offset = local_start.utcoffset()
    if offset is None:
        offset = timezone.utc.utcoffset(local_start)
    fixed_home_tz = timezone(offset, name=zone_name)
    start_utc = local_start.astimezone(timezone.utc)
    offset_seconds = int(offset.total_seconds())

    return start_utc, fixed_home_tz, {
        "iana_name": zone_name,
        "utc_offset": _offset_label(offset_seconds),
        "description": f"{zone_name} (UTC{_offset_label(offset_seconds)} at departure)",
        "method": "A single home-terminal offset resolved at departure is used for every generated log page.",
    }


def _enrich_segment_locations(segments, route, current, pickup, dropoff) -> list[str]:
    """Replace route-mile placeholders with city/state remarks where possible."""

    warnings: list[str] = []
    route_miles = route["miles"]
    geometry = route["geometry"]
    pickup_mile = route["legs"][0]["miles"]
    resolved: dict[float, str] = {}

    for segment in segments:
        mile_key = round(segment.start_mile, 1)
        if segment.event_type == "pickup":
            segment.location = pickup["short_name"]
            continue
        if segment.event_type == "dropoff":
            segment.location = dropoff["short_name"]
            continue
        if abs(segment.start_mile) < 0.05:
            segment.location = current["short_name"]
            continue
        if abs(segment.start_mile - pickup_mile) < 0.05:
            segment.location = pickup["short_name"]
            continue
        if abs(segment.start_mile - route_miles) < 0.05:
            segment.location = dropoff["short_name"]
            continue
        if mile_key in resolved:
            segment.location = resolved[mile_key]
            continue

        position = interpolate_route_position(geometry, route_miles, segment.start_mile)
        try:
            location = reverse_geocode(position["lat"], position["lon"])
        except MappingServiceError:
            location = ""
            if not warnings:
                warnings.append(
                    "Some en-route remarks use route-mile references because reverse geocoding was unavailable."
                )

        if location:
            segment.location = location
            resolved[mile_key] = location
        elif not warnings:
            warnings.append(
                "Some en-route remarks use route-mile references because a nearby city/state could not be resolved."
            )

    return warnings


def _output_integrity_issues(segments, daily_logs, route) -> list[str]:
    """Cross-check generated output against the map route and log pages."""

    issues: list[str] = []
    scheduled_miles = sum(segment.miles for segment in segments if segment.status == DRIVING)
    scheduled_driving_hours = sum(
        segment.duration_hours for segment in segments if segment.status == DRIVING
    )

    if abs(scheduled_miles - route["miles"]) > 0.2:
        issues.append("Scheduled driving miles do not match the mapped route distance.")
    if abs(scheduled_driving_hours - route["driving_hours"]) > 0.01:
        issues.append("Scheduled driving time does not match the mapped route duration.")

    displayed_daily_miles = sum(float(log["miles_driven"]) for log in daily_logs)
    if abs(displayed_daily_miles - round(route["miles"], 1)) > 0.11:
        issues.append("Displayed daily mileage totals do not reconcile with the mapped route.")

    route_leg_miles = sum(float(leg["miles"]) for leg in route.get("legs", []))
    route_leg_hours = sum(float(leg["driving_hours"]) for leg in route.get("legs", []))
    if abs(route_leg_miles - route["miles"]) > 0.2:
        issues.append("Mapped route-leg miles do not reconcile with the route total.")
    if abs(route_leg_hours - route["driving_hours"]) > 0.01:
        issues.append("Mapped route-leg durations do not reconcile with the route total.")

    for daily_log in daily_logs:
        if abs(daily_log["total_logged_hours"] - 24.0) > 0.01:
            issues.append(f"Daily log {daily_log['date']} does not total 24 hours.")
        if abs(sum(daily_log["totals_hours"].values()) - 24.0) > 0.001:
            issues.append(f"Displayed status totals for {daily_log['date']} do not add to 24 hours.")
        if not daily_log["segments"]:
            issues.append(f"Daily log {daily_log['date']} has no duty-status graph data.")
            continue
        if abs(daily_log["segments"][0]["start_hour"]) > 0.001:
            issues.append(f"Daily log {daily_log['date']} does not begin at 00:00.")
        if abs(daily_log["segments"][-1]["end_hour"] - 24.0) > 0.001:
            issues.append(f"Daily log {daily_log['date']} does not end at 24:00.")
        for previous, current in zip(daily_log["segments"], daily_log["segments"][1:]):
            if abs(previous["end_hour"] - current["start_hour"]) > 0.001:
                issues.append(f"Daily log {daily_log['date']} contains a graph gap or overlap.")
                break

    return sorted(set(issues))


def _build_events(segments, geometry, route_miles, display_tz):
    events = []
    for segment in segments:
        if segment.status == DRIVING:
            continue
        position = interpolate_route_position(geometry, route_miles, segment.start_mile)
        item = segment.to_dict(display_tz)
        events.append(
            {
                "event_type": segment.event_type,
                "label": segment.label,
                "location": segment.location,
                "start": item["start"],
                "end": item["end"],
                "start_display": item["start_display"],
                "end_display": item["end_display"],
                "duration_hours": round(segment.duration_hours, 2),
                "route_mile": round(segment.start_mile, 1),
                "lat": round(position["lat"], 6),
                "lon": round(position["lon"], 6),
            }
        )
    return events


@api_view(["GET"])
def health(_request):
    return Response({"status": "ok", "service": "RouteDuty API"})


@api_view(["POST"])
def plan_trip(request):
    serializer = TripRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data

    try:
        current = geocode(values["current_location"])
        pickup = geocode(values["pickup_location"])
        dropoff = geocode(values["dropoff_location"])
    except MappingServiceError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    missing = [
        label
        for label, location in (
            ("current location", current),
            ("pickup location", pickup),
            ("drop-off location", dropoff),
        )
        if location is None
    ]
    if missing:
        return Response(
            {"error": f"Could not find: {', '.join(missing)}. Add a city and state abbreviation."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        route = route_between([current, pickup, dropoff])
    except MappingServiceError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    if route is None or len(route.get("legs", [])) != 2 or not route.get("geometry"):
        return Response(
            {"error": "Could not compute a drivable road route through all three locations."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    start_utc, display_tz, time_basis = _resolve_time_basis(
        values.get("start_time_local", ""),
        values.get("home_terminal_timezone", "UTC"),
    )

    logbook = {
        "driver_name": values.get("driver_name", ""),
        "co_driver_name": values.get("co_driver_name", ""),
        "carrier_name": values.get("carrier_name", ""),
        "main_office_address": values.get("main_office_address", ""),
        "home_terminal_address": values.get("home_terminal_address", ""),
        "vehicle_numbers": values.get("vehicle_numbers", ""),
        "shipping_document_number": values.get("shipping_document_number", ""),
        "manifest_number": values.get("manifest_number", ""),
        "shipper_commodity": values.get("shipper_commodity", ""),
        "from_location": current["short_name"],
        "to_location": dropoff["short_name"],
        "home_terminal_time_basis": time_basis["description"],
    }

    try:
        segments = build_trip_plan(
            start_time=start_utc,
            legs=route["legs"],
            current_cycle_used_hours=values["current_cycle_used"],
            current_location=values["current_location"],
            pickup_location=values["pickup_location"],
            dropoff_location=values["dropoff_location"],
        )
    except (ValueError, RuntimeError) as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    mapping_warnings = _enrich_segment_locations(segments, route, current, pickup, dropoff)
    daily_logs = split_segments_by_day(
        segments,
        logbook,
        display_tz=display_tz,
        initial_cycle_used=values["current_cycle_used"],
    )
    events = _build_events(segments, route["geometry"], route["miles"], display_tz)
    validation_issues = validate_plan(
        segments,
        initial_cycle_used=values["current_cycle_used"],
    )
    validation_issues.extend(_output_integrity_issues(segments, daily_logs, route))
    validation_issues = sorted(set(validation_issues))

    # Never return a schedule that fails the independent replay or output
    # integrity checks. This turns calculation regressions into an explicit
    # server error instead of presenting a potentially non-compliant plan.
    if validation_issues:
        return Response(
            {
                "error": "The generated trip did not pass the internal HOS validation.",
                "details": validation_issues,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    zone = ZoneInfo(time_basis["iana_name"])
    departure_offset = segments[0].start.astimezone(zone).utcoffset()
    completion_offset = segments[-1].end.astimezone(zone).utcoffset()
    if departure_offset != completion_offset:
        mapping_warnings.append(
            "This trip crosses a daylight-saving offset change. The supplied 24-hour paper-log template "
            "is rendered with the departure home-terminal offset; review the transition before operational use."
        )

    total_elapsed_hours = (segments[-1].end - segments[0].start).total_seconds() / 3600
    total_driving_hours = sum(
        segment.duration_hours for segment in segments if segment.status == DRIVING
    )
    end_cycle_used = segments[-1].cycle_used_end

    counts = {
        "fuel_stops": sum(segment.event_type == "fuel" for segment in segments),
        "hos_breaks": sum(segment.event_type == "break" for segment in segments),
        "ten_hour_rests": sum(segment.event_type == "rest" for segment in segments),
        "cycle_restarts": sum(segment.event_type == "restart" for segment in segments),
    }

    return Response(
        {
            "locations": {"current": current, "pickup": pickup, "dropoff": dropoff},
            "time_basis": time_basis,
            "route": {
                "distance_miles": round(route["miles"], 1),
                "geometry": route["geometry"],
                "map_estimated_hours": round(route["map_duration_hours"], 2),
                "legs": [
                    {
                        **leg,
                        "miles": round(leg["miles"], 1),
                        "driving_hours": round(leg["driving_hours"], 2),
                        "map_duration_hours": round(leg["map_duration_hours"], 2),
                    }
                    for leg in route["legs"]
                ],
                "events": events,
            },
            "trip_summary": {
                "total_miles": round(route["miles"], 1),
                "total_trip_hours": round(total_elapsed_hours, 2),
                "total_driving_hours": round(total_driving_hours, 2),
                "num_log_days": len(daily_logs),
                "start_time": segments[0].start.isoformat(),
                "end_time": segments[-1].end.isoformat(),
                "start_display": segments[0].to_dict(display_tz)["start_display"],
                "end_display": segments[-1].to_dict(display_tz)["end_display"],
                "cycle_used_at_end": round(end_cycle_used, 2),
                "cycle_hours_available_at_end": round(max(0.0, 70.0 - end_cycle_used), 2),
                **counts,
            },
            "itinerary": [segment.to_dict(display_tz) for segment in segments],
            "daily_logs": daily_logs,
            "validation": {
                "passed": not validation_issues,
                "issues": validation_issues,
                "warnings": mapping_warnings,
            },
            "assumptions": [
                "Property-carrying driver on the 70-hour/8-day schedule, beginning after a qualifying 10-hour off-duty period.",
                "Driving uses the routing service's estimated duration; the road route is not commercial-truck-specific navigation.",
                "No adverse-driving, short-haul, or split-sleeper exception is applied.",
                "Pickup and drop-off each require one hour on duty, not driving.",
                "Fueling is scheduled for 30 on-duty minutes at every 1,000 route miles and also satisfies the 30-minute driving interruption.",
                "The trip begins with zero miles since the last fuel event, because that prior value is not supplied by the assessment.",
                "Because prior daily cycle records are not supplied, current cycle use is treated as a conservative balance and a 34-hour restart is used when driving eligibility is exhausted.",
                "En-route markers are approximate route positions with nearby city/state remarks; the driver or carrier must verify a safe, legal, suitable fuel or parking facility.",
                time_basis["method"],
            ],
        }
    )
