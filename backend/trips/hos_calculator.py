"""Hours-of-Service planning engine for the RouteDuty assessment.

The engine implements the assessment's property-carrying assumptions:

* 11 driving hours after a qualifying 10-hour reset.
* No driving after the 14th consecutive hour after coming on duty.
* A 30-minute consecutive non-driving interruption after 8 cumulative
  driving hours.
* A 70-hour / 8-day cycle, represented conservatively because the assessment
  supplies only one aggregate ``current_cycle_used`` value rather than the
  preceding eight daily records.
* A 34-hour restart when that conservative cycle balance is exhausted.
* One hour on duty for pickup and one hour on duty for drop-off.
* A 30-minute on-duty fuel stop whenever 1,000 route miles have accumulated.

Important distinction: the 14-hour and 70-hour limits prohibit additional
*driving*. They do not prohibit non-driving work. Pickup, drop-off, and fuel
service therefore finish normally; a reset is inserted only before the next
period of driving when required.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone, tzinfo
from typing import Iterable

DRIVING = "driving"
ON_DUTY = "on_duty"
OFF_DUTY = "off_duty"
SLEEPER = "sleeper_berth"

MAX_DRIVE_PER_DUTY_PERIOD = 11.0
MAX_DRIVING_WINDOW = 14.0
BREAK_AFTER_DRIVING = 8.0
BREAK_DURATION = 0.5
DAILY_RESET = 10.0
CYCLE_LIMIT = 70.0
CYCLE_RESTART = 34.0
FUEL_INTERVAL_MILES = 1000.0
FUEL_DURATION = 0.5
PICKUP_DURATION = 1.0
DROPOFF_DURATION = 1.0
FALLBACK_SPEED_MPH = 55.0
EPSILON = 1e-7


@dataclass
class Segment:
    status: str
    start: datetime
    end: datetime
    label: str
    location: str
    event_type: str
    miles: float = 0.0
    start_mile: float = 0.0
    end_mile: float = 0.0
    leg_index: int | None = None
    cycle_used_start: float = 0.0
    cycle_used_end: float = 0.0

    @property
    def duration_hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600

    def to_dict(self, display_tz: tzinfo = timezone.utc) -> dict:
        start_local = self.start.astimezone(display_tz)
        end_local = self.end.astimezone(display_tz)
        return {
            "status": self.status,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "start_local": start_local.isoformat(),
            "end_local": end_local.isoformat(),
            "start_display": _format_datetime(start_local),
            "end_display": _format_datetime(end_local),
            "label": self.label,
            "location": self.location,
            "event_type": self.event_type,
            "duration_hours": round(self.duration_hours, 4),
            "miles": round(self.miles, 1),
            "start_mile": round(self.start_mile, 1),
            "end_mile": round(self.end_mile, 1),
            "leg_index": self.leg_index,
            "cycle_used_start": round(self.cycle_used_start, 2),
            "cycle_used_end": round(self.cycle_used_end, 2),
        }


def _format_datetime(value: datetime) -> str:
    return value.strftime("%b %d, %Y · %I:%M %p").replace(" 0", " ")


def _hours_between(start: datetime | None, end: datetime) -> float:
    if start is None:
        return 0.0
    return (end - start).total_seconds() / 3600


def _normalise_legs(legs: list[dict]) -> list[dict]:
    if len(legs) != 2:
        raise ValueError("Exactly two route legs are required.")

    normalised: list[dict] = []
    for leg in legs:
        miles = float(leg.get("miles", 0.0))
        driving_hours = float(leg.get("driving_hours", leg.get("map_duration_hours", 0.0)))
        if not math.isfinite(miles) or not math.isfinite(driving_hours):
            raise ValueError("Route distance and duration must be finite numbers.")
        miles = max(0.0, miles)
        if miles > EPSILON and driving_hours <= EPSILON:
            driving_hours = miles / FALLBACK_SPEED_MPH
        if miles <= EPSILON:
            driving_hours = 0.0
        normalised.append(
            {
                **leg,
                "miles": miles,
                "driving_hours": max(0.0, driving_hours),
                "from_name": str(leg.get("from_name", "Origin")),
                "to_name": str(leg.get("to_name", "Destination")),
            }
        )
    return normalised


def build_trip_plan(
    *,
    start_time: datetime,
    legs: list[dict],
    current_cycle_used_hours: float,
    current_location: str,
    pickup_location: str,
    dropoff_location: str,
) -> list[Segment]:
    """Create a continuous HOS-compliant schedule.

    ``start_time`` must be timezone-aware. Driving durations come from the map
    route service, while route miles are distributed proportionally across each
    leg. Non-driving work is never incorrectly blocked by the 14-hour or
    70-hour driving prohibitions.
    """

    if start_time.tzinfo is None:
        raise ValueError("start_time must be timezone-aware.")
    if not 0.0 <= float(current_cycle_used_hours) <= CYCLE_LIMIT:
        raise ValueError("current_cycle_used_hours must be between 0 and 70.")

    legs = _normalise_legs(legs)
    segments: list[Segment] = []
    clock = start_time
    cycle_used = float(current_cycle_used_hours)
    drive_in_period = 0.0
    drive_since_break = 0.0
    duty_start: datetime | None = None
    trip_mile = 0.0
    miles_since_fuel = 0.0

    def fallback_location(target: str) -> str:
        return f"Near route mile {trip_mile:.1f} toward {target}"

    def add_segment(
        status: str,
        hours: float,
        label: str,
        location: str,
        event_type: str,
        *,
        miles: float = 0.0,
        leg_index: int | None = None,
    ) -> Segment:
        nonlocal clock, cycle_used, drive_in_period, drive_since_break, duty_start, trip_mile

        if hours <= EPSILON:
            raise ValueError(f"Segment duration must be positive: {label}")

        start = clock
        end = start + timedelta(hours=hours)
        start_mile = trip_mile
        end_mile = trip_mile + miles
        cycle_before = cycle_used

        if status in (DRIVING, ON_DUTY):
            if duty_start is None:
                duty_start = start
            cycle_used += hours

        if status == DRIVING:
            drive_in_period += hours
            drive_since_break += hours
            trip_mile = end_mile
        elif hours >= BREAK_DURATION - EPSILON:
            # Off duty, sleeper berth, or on-duty/not-driving can satisfy the
            # 30-minute interruption requirement when consecutive.
            drive_since_break = 0.0

        segment = Segment(
            status=status,
            start=start,
            end=end,
            label=label,
            location=location,
            event_type=event_type,
            miles=miles,
            start_mile=start_mile,
            end_mile=end_mile,
            leg_index=leg_index,
            cycle_used_start=cycle_before,
            cycle_used_end=cycle_used,
        )
        segments.append(segment)
        clock = end
        return segment

    def reset_daily_clocks() -> None:
        nonlocal drive_in_period, drive_since_break, duty_start
        drive_in_period = 0.0
        drive_since_break = 0.0
        duty_start = None

    def add_daily_reset(target: str) -> None:
        add_segment(
            SLEEPER,
            DAILY_RESET,
            "Required 10-hour rest",
            fallback_location(target),
            "rest",
        )
        reset_daily_clocks()

    def add_cycle_restart(target: str) -> None:
        nonlocal cycle_used
        segment = add_segment(
            OFF_DUTY,
            CYCLE_RESTART,
            "34-hour cycle restart",
            fallback_location(target),
            "restart",
        )
        cycle_used = 0.0
        segment.cycle_used_end = 0.0
        reset_daily_clocks()

    def ensure_ready_to_drive(target: str) -> None:
        """Insert only the rest required before another driving period."""

        while True:
            if cycle_used >= CYCLE_LIMIT - EPSILON:
                add_cycle_restart(target)
                continue

            elapsed = _hours_between(duty_start, clock)
            if (
                drive_in_period >= MAX_DRIVE_PER_DUTY_PERIOD - EPSILON
                or (duty_start is not None and elapsed >= MAX_DRIVING_WINDOW - EPSILON)
            ):
                add_daily_reset(target)
                continue

            if drive_since_break >= BREAK_AFTER_DRIVING - EPSILON:
                window_remaining = (
                    MAX_DRIVING_WINDOW - elapsed if duty_start is not None else MAX_DRIVING_WINDOW
                )
                driving_after_break = min(
                    MAX_DRIVE_PER_DUTY_PERIOD - drive_in_period,
                    window_remaining - BREAK_DURATION,
                    CYCLE_LIMIT - cycle_used,
                )
                if driving_after_break <= EPSILON:
                    add_daily_reset(target)
                else:
                    add_segment(
                        OFF_DUTY,
                        BREAK_DURATION,
                        "30-minute HOS break",
                        fallback_location(target),
                        "break",
                    )
                continue

            return

    def add_service(duration: float, label: str, place: str, event_type: str) -> None:
        # The 14-hour and 70-hour rules restrict driving, not non-driving work.
        add_segment(ON_DUTY, duration, label, place, event_type)

    def add_fuel_stop(target: str) -> None:
        nonlocal miles_since_fuel
        add_segment(
            ON_DUTY,
            FUEL_DURATION,
            "Fuel stop",
            fallback_location(target),
            "fuel",
        )
        miles_since_fuel = 0.0

    for leg_index, leg in enumerate(legs):
        leg_remaining_miles = leg["miles"]
        leg_remaining_hours = leg["driving_hours"]
        target = leg["to_name"]
        origin = leg["from_name"]
        first_drive_piece = True
        loop_guard = 0

        while leg_remaining_miles > 0.01 or leg_remaining_hours > 0.0001:
            loop_guard += 1
            if loop_guard > 10_000:
                raise RuntimeError("Trip planner could not converge on a driving schedule.")

            ensure_ready_to_drive(target)

            elapsed = _hours_between(duty_start, clock)
            hours_to_drive_limit = MAX_DRIVE_PER_DUTY_PERIOD - drive_in_period
            hours_to_window = (
                MAX_DRIVING_WINDOW - elapsed if duty_start is not None else MAX_DRIVING_WINDOW
            )
            hours_to_break = BREAK_AFTER_DRIVING - drive_since_break
            hours_to_cycle = CYCLE_LIMIT - cycle_used
            hours_to_destination = leg_remaining_hours

            if leg_remaining_miles > EPSILON and leg_remaining_hours > EPSILON:
                hours_per_mile = leg_remaining_hours / leg_remaining_miles
                miles_to_fuel = max(0.0, FUEL_INTERVAL_MILES - miles_since_fuel)
                hours_to_fuel = miles_to_fuel * hours_per_mile
            else:
                hours_to_fuel = float("inf")

            drive_hours = min(
                hours_to_drive_limit,
                hours_to_window,
                hours_to_break,
                hours_to_cycle,
                hours_to_destination,
                hours_to_fuel,
            )

            if drive_hours <= EPSILON:
                if miles_since_fuel >= FUEL_INTERVAL_MILES - 0.01:
                    add_fuel_stop(target)
                elif hours_to_cycle <= EPSILON:
                    add_cycle_restart(target)
                elif hours_to_drive_limit <= EPSILON or hours_to_window <= EPSILON:
                    add_daily_reset(target)
                elif hours_to_break <= EPSILON:
                    # Re-entering ensure_ready_to_drive selects a short break
                    # or full reset based on the remaining 14-hour window.
                    ensure_ready_to_drive(target)
                elif hours_to_destination <= EPSILON:
                    leg_remaining_hours = 0.0
                    leg_remaining_miles = 0.0
                continue

            if drive_hours >= leg_remaining_hours - EPSILON:
                miles_this_segment = leg_remaining_miles
                drive_hours = leg_remaining_hours
            else:
                miles_per_hour = leg_remaining_miles / max(leg_remaining_hours, EPSILON)
                miles_this_segment = min(leg_remaining_miles, drive_hours * miles_per_hour)

            label = (
                f"Drive from {origin} to {target}"
                if first_drive_piece
                else f"Continue toward {target}"
            )
            add_segment(
                DRIVING,
                drive_hours,
                label,
                origin if first_drive_piece else fallback_location(target),
                "drive",
                miles=miles_this_segment,
                leg_index=leg_index,
            )
            first_drive_piece = False
            leg_remaining_hours = max(0.0, leg_remaining_hours - drive_hours)
            leg_remaining_miles = max(0.0, leg_remaining_miles - miles_this_segment)
            miles_since_fuel += miles_this_segment

            # A 30-minute fuel stop is itself a qualifying interruption of
            # driving. It is inserted at every full 1,000-mile threshold,
            # including a threshold reached at a pickup or final destination.
            if miles_since_fuel >= FUEL_INTERVAL_MILES - 0.01:
                add_fuel_stop(target)

        if leg_index == 0:
            add_service(PICKUP_DURATION, "Pickup and loading", pickup_location, "pickup")
        else:
            add_service(DROPOFF_DURATION, "Drop-off and unloading", dropoff_location, "dropoff")

    return segments


def _clip_segment_to_day(
    segment: Segment,
    segment_index: int,
    day_start_utc: datetime,
    day_end_utc: datetime,
    day_start_local: datetime,
    display_tz: tzinfo,
) -> dict | None:
    piece_start = max(segment.start, day_start_utc)
    piece_end = min(segment.end, day_end_utc)
    if piece_start >= piece_end:
        return None

    full_seconds = max((segment.end - segment.start).total_seconds(), EPSILON)
    piece_fraction = (piece_end - piece_start).total_seconds() / full_seconds
    piece_miles = segment.miles * piece_fraction
    local_start = piece_start.astimezone(display_tz)
    local_end = piece_end.astimezone(display_tz)
    end_hour = 24.0 if piece_end == day_end_utc else (local_end - day_start_local).total_seconds() / 3600

    return {
        "segment_index": segment_index,
        "status": segment.status,
        "start": piece_start.isoformat(),
        "end": piece_end.isoformat(),
        "start_local": local_start.isoformat(),
        "end_local": local_end.isoformat(),
        "start_hour": round((local_start - day_start_local).total_seconds() / 3600, 6),
        "end_hour": round(end_hour, 6),
        "label": segment.label,
        "location": segment.location,
        "event_type": segment.event_type,
        "miles": round(piece_miles, 3),
        "start_mile": round(segment.start_mile, 1),
        "end_mile": round(segment.end_mile, 1),
        "is_filler": False,
        "is_segment_start": piece_start == segment.start,
        "is_segment_end": piece_end == segment.end,
    }


def _off_duty_filler(
    start: datetime,
    end: datetime,
    day_start_local: datetime,
    day_end_utc: datetime,
    display_tz: tzinfo,
) -> dict:
    local_start = start.astimezone(display_tz)
    local_end = end.astimezone(display_tz)
    end_hour = 24.0 if end == day_end_utc else (local_end - day_start_local).total_seconds() / 3600
    return {
        "segment_index": None,
        "status": OFF_DUTY,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "start_local": local_start.isoformat(),
        "end_local": local_end.isoformat(),
        "start_hour": round((local_start - day_start_local).total_seconds() / 3600, 6),
        "end_hour": round(end_hour, 6),
        "label": "Off duty",
        "location": "",
        "event_type": "off_duty",
        "miles": 0.0,
        "start_mile": 0.0,
        "end_mile": 0.0,
        "is_filler": True,
        "is_segment_start": False,
        "is_segment_end": False,
    }


def split_segments_by_day(
    segments: Iterable[Segment],
    logbook: dict,
    *,
    display_tz: tzinfo = timezone.utc,
    initial_cycle_used: float = 0.0,
) -> list[dict]:
    """Return complete midnight-to-midnight daily logs.

    The caller supplies a fixed home-terminal time basis, so each graph is a
    true 24-hour page and never changes according to the reviewer's browser.
    """

    segments = list(segments)
    if not segments:
        return []

    first_local_date = segments[0].start.astimezone(display_tz).date()
    last_instant = segments[-1].end - timedelta(microseconds=1)
    last_local_date = last_instant.astimezone(display_tz).date()

    daily_logs: list[dict] = []
    current_date = first_local_date
    cycle_used = float(initial_cycle_used)

    while current_date <= last_local_date:
        day_start_local = datetime.combine(current_date, time.min, tzinfo=display_tz)
        day_end_local = day_start_local + timedelta(days=1)
        day_start_utc = day_start_local.astimezone(timezone.utc)
        day_end_utc = day_end_local.astimezone(timezone.utc)

        pieces = []
        for index, segment in enumerate(segments):
            piece = _clip_segment_to_day(
                segment,
                index,
                day_start_utc,
                day_end_utc,
                day_start_local,
                display_tz,
            )
            if piece is not None:
                pieces.append(piece)
        pieces.sort(key=lambda item: item["start"])

        complete: list[dict] = []
        cursor = day_start_utc
        for piece in pieces:
            piece_start = datetime.fromisoformat(piece["start"])
            if cursor < piece_start:
                complete.append(
                    _off_duty_filler(
                        cursor,
                        piece_start,
                        day_start_local,
                        day_end_utc,
                        display_tz,
                    )
                )
            complete.append(piece)
            cursor = datetime.fromisoformat(piece["end"])

        if cursor < day_end_utc:
            complete.append(
                _off_duty_filler(
                    cursor,
                    day_end_utc,
                    day_start_local,
                    day_end_utc,
                    display_tz,
                )
            )

        totals = {DRIVING: 0.0, ON_DUTY: 0.0, OFF_DUTY: 0.0, SLEEPER: 0.0}
        miles_today = 0.0
        remarks: list[dict] = []
        cycle_start = cycle_used
        restart_completed = False

        for piece in complete:
            duration = (
                datetime.fromisoformat(piece["end"]) - datetime.fromisoformat(piece["start"])
            ).total_seconds() / 3600
            totals[piece["status"]] += duration
            miles_today += piece["miles"]

            if piece["status"] in (DRIVING, ON_DUTY):
                cycle_used += duration
            if piece["event_type"] == "restart" and piece["is_segment_end"]:
                cycle_used = 0.0
                restart_completed = True

            if not piece["is_filler"] and piece["is_segment_start"]:
                # A segment clipped at midnight is a continuation, not a new
                # duty-status change. Remarks therefore appear only where the
                # underlying itinerary event actually begins.
                local_start = datetime.fromisoformat(piece["start"]).astimezone(display_tz)
                remarks.append(
                    {
                        "time": local_start.strftime("%H:%M"),
                        "status": piece["status"],
                        "label": piece["label"],
                        "location": piece["location"],
                    }
                )

        # The page is filled with off-duty time after the planned trip ends.
        # That transition is real and should be present in Remarks even though
        # the filler is not part of the route itinerary.
        final_segment = segments[-1]
        if day_start_utc <= final_segment.end < day_end_utc:
            final_local = final_segment.end.astimezone(display_tz)
            if final_segment.end != day_end_utc:
                remarks.append(
                    {
                        "time": final_local.strftime("%H:%M"),
                        "status": OFF_DUTY,
                        "label": "Trip complete — off duty",
                        "location": final_segment.location,
                    }
                )

        rounded_totals = {key: round(value, 2) for key, value in totals.items()}
        # Make the numbers printed beside the four graph lines reconcile to
        # exactly 24.00 after two-decimal rounding. Any correction is at most a
        # few hundredths and is applied to the day's largest status bucket.
        rounding_difference = round(24.0 - sum(rounded_totals.values()), 2)
        if abs(rounding_difference) >= 0.001:
            adjustment_status = max(totals, key=totals.get)
            rounded_totals[adjustment_status] = round(
                rounded_totals[adjustment_status] + rounding_difference,
                2,
            )

        on_duty_today = totals[DRIVING] + totals[ON_DUTY]
        daily_logs.append(
            {
                "date": current_date.isoformat(),
                "date_parts": {
                    "month": current_date.month,
                    "day": current_date.day,
                    "year": current_date.year,
                },
                "segments": complete,
                "totals_hours": rounded_totals,
                "total_logged_hours": round(sum(totals.values()), 2),
                "miles_driven": round(miles_today, 1),
                "remarks": remarks,
                "logbook": logbook,
                "cycle_recap": {
                    "cycle_used_start": round(cycle_start, 2),
                    "on_duty_hours_today": round(on_duty_today, 2),
                    "cycle_used_end": round(cycle_used, 2),
                    "cycle_hours_available_end": round(max(0.0, CYCLE_LIMIT - cycle_used), 2),
                    "restart_completed": restart_completed,
                },
            }
        )

        current_date += timedelta(days=1)

    # Reconcile one-decimal daily mileage totals with the mapped trip mileage.
    # The correction is only the accumulated display-rounding difference.
    route_miles = round(sum(segment.miles for segment in segments if segment.status == DRIVING), 1)
    displayed_miles = round(sum(log["miles_driven"] for log in daily_logs), 1)
    mileage_difference = round(route_miles - displayed_miles, 1)
    if abs(mileage_difference) >= 0.05 and daily_logs:
        adjustment_log = next(
            (log for log in reversed(daily_logs) if log["miles_driven"] > 0),
            daily_logs[-1],
        )
        adjustment_log["miles_driven"] = round(
            max(0.0, adjustment_log["miles_driven"] + mileage_difference),
            1,
        )

    return daily_logs


def validate_plan(
    segments: Iterable[Segment],
    *,
    initial_cycle_used: float = 0.0,
) -> list[str]:
    """Independently replay a schedule and report any HOS inconsistency."""

    segments = list(segments)
    issues: list[str] = []
    if not segments:
        return ["No schedule segments were generated."]

    for previous, current in zip(segments, segments[1:]):
        if previous.end != current.start:
            issues.append("The generated schedule contains a time gap or overlap.")
            break

    drive_in_period = 0.0
    drive_since_break = 0.0
    duty_start: datetime | None = None
    cycle_used = float(initial_cycle_used)
    miles_since_fuel = 0.0

    for segment in segments:
        duration = segment.duration_hours
        if segment.status in (DRIVING, ON_DUTY) and duty_start is None:
            duty_start = segment.start

        if segment.status == DRIVING:
            if cycle_used >= CYCLE_LIMIT - EPSILON:
                issues.append("Driving begins after the 70-hour cycle limit is reached.")
            if cycle_used + duration > CYCLE_LIMIT + 0.01:
                issues.append("Driving exceeds the available 70-hour cycle balance.")
            if drive_in_period + duration > MAX_DRIVE_PER_DUTY_PERIOD + 0.01:
                issues.append("A duty period exceeds 11 driving hours.")
            if drive_since_break + duration > BREAK_AFTER_DRIVING + 0.01:
                issues.append("More than 8 cumulative driving hours occur without a break.")
            if duty_start and _hours_between(duty_start, segment.end) > MAX_DRIVING_WINDOW + 0.01:
                issues.append("Driving occurs outside the 14-hour window.")

            drive_in_period += duration
            drive_since_break += duration
            cycle_used += duration
            miles_since_fuel += segment.miles
            if miles_since_fuel > FUEL_INTERVAL_MILES + 0.1:
                issues.append("More than 1,000 route miles occur without a fuel stop.")

        elif segment.status == ON_DUTY:
            cycle_used += duration
            if duration >= BREAK_DURATION - EPSILON:
                drive_since_break = 0.0
        elif duration >= BREAK_DURATION - EPSILON:
            drive_since_break = 0.0

        if segment.event_type == "fuel":
            if segment.status != ON_DUTY or duration < BREAK_DURATION - EPSILON:
                issues.append("Fuel stops must be at least 30 minutes on duty, not driving.")
            miles_since_fuel = 0.0

        if segment.event_type == "rest":
            if duration < DAILY_RESET - EPSILON:
                issues.append("A daily reset is shorter than 10 consecutive hours.")
            drive_in_period = 0.0
            drive_since_break = 0.0
            duty_start = None

        if segment.event_type == "restart":
            if duration < CYCLE_RESTART - EPSILON:
                issues.append("A cycle restart is shorter than 34 consecutive hours.")
            cycle_used = 0.0
            drive_in_period = 0.0
            drive_since_break = 0.0
            duty_start = None

    if miles_since_fuel > FUEL_INTERVAL_MILES + 0.1:
        issues.append("The trip ends more than 1,000 route miles after the last fuel stop.")

    return sorted(set(issues))
