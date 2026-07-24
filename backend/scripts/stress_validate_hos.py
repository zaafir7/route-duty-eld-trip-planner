"""Reproducible independent stress validation for the pure HOS engine.

Run from the backend directory:

    python scripts/stress_validate_hos.py --iterations 20000

This script deliberately does not call ``validate_plan`` for its main replay;
it tracks the HOS clocks independently and then also confirms that the
application validator agrees.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from trips import hos_calculator as hos  # noqa: E402


def _build_random_plan(generator: random.Random):
    first_miles = generator.uniform(0, 2500)
    second_miles = generator.uniform(0, 6000)
    first_hours = 0.0 if first_miles < 1e-9 else first_miles / generator.uniform(25, 75)
    second_hours = 0.0 if second_miles < 1e-9 else second_miles / generator.uniform(25, 75)
    cycle_used = generator.uniform(0, 70)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        minutes=generator.randrange(525_600)
    )
    plan = hos.build_trip_plan(
        start_time=start,
        legs=[
            {
                "miles": first_miles,
                "driving_hours": first_hours,
                "from_name": "Current",
                "to_name": "Pickup",
            },
            {
                "miles": second_miles,
                "driving_hours": second_hours,
                "from_name": "Pickup",
                "to_name": "Drop-off",
            },
        ],
        current_cycle_used_hours=cycle_used,
        current_location="Current",
        pickup_location="Pickup",
        dropoff_location="Drop-off",
    )
    return plan, first_miles + second_miles, first_hours + second_hours, cycle_used


def _independent_replay(segments, initial_cycle_used: float) -> None:
    duty_start = None
    drive_in_period = 0.0
    drive_since_break = 0.0
    cycle_used = initial_cycle_used
    miles_since_fuel = 0.0

    for index, segment in enumerate(segments):
        duration = segment.duration_hours
        assert duration > 0
        if index:
            assert segments[index - 1].end == segment.start

        if segment.status in (hos.DRIVING, hos.ON_DUTY) and duty_start is None:
            duty_start = segment.start

        if segment.status == hos.DRIVING:
            assert cycle_used + duration <= hos.CYCLE_LIMIT + 0.0001
            assert drive_in_period + duration <= hos.MAX_DRIVE_PER_DUTY_PERIOD + 0.0001
            assert drive_since_break + duration <= hos.BREAK_AFTER_DRIVING + 0.0001
            assert duty_start is not None
            elapsed = (segment.end - duty_start).total_seconds() / 3600
            assert elapsed <= hos.MAX_DRIVING_WINDOW + 0.0001

            cycle_used += duration
            drive_in_period += duration
            drive_since_break += duration
            miles_since_fuel += segment.miles
            assert miles_since_fuel <= hos.FUEL_INTERVAL_MILES + 0.1001
        elif segment.status == hos.ON_DUTY:
            cycle_used += duration
            if duration >= hos.BREAK_DURATION - hos.EPSILON:
                drive_since_break = 0.0
        elif duration >= hos.BREAK_DURATION - hos.EPSILON:
            drive_since_break = 0.0

        if segment.event_type == "fuel":
            assert segment.status == hos.ON_DUTY
            assert duration >= hos.FUEL_DURATION - hos.EPSILON
            miles_since_fuel = 0.0
        if segment.event_type == "rest":
            assert duration >= hos.DAILY_RESET - hos.EPSILON
            duty_start = None
            drive_in_period = 0.0
            drive_since_break = 0.0
        if segment.event_type == "restart":
            assert duration >= hos.CYCLE_RESTART - hos.EPSILON
            cycle_used = 0.0
            duty_start = None
            drive_in_period = 0.0
            drive_since_break = 0.0

    assert miles_since_fuel <= hos.FUEL_INTERVAL_MILES + 0.1001


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260722)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be at least 1")

    generator = random.Random(args.seed)
    for index in range(args.iterations):
        plan, expected_miles, expected_hours, cycle_used = _build_random_plan(generator)
        _independent_replay(plan, cycle_used)
        assert hos.validate_plan(plan, initial_cycle_used=cycle_used) == []
        assert math.isclose(
            sum(item.miles for item in plan if item.status == hos.DRIVING),
            expected_miles,
            abs_tol=0.003,
        )
        assert math.isclose(
            sum(item.duration_hours for item in plan if item.status == hos.DRIVING),
            expected_hours,
            abs_tol=0.00001,
        )

        if index % 10 == 0:
            logs = hos.split_segments_by_day(
                plan,
                {},
                display_tz=timezone(timedelta(hours=-5)),
                initial_cycle_used=cycle_used,
            )
            assert round(sum(log["miles_driven"] for log in logs), 1) == round(expected_miles, 1)
            for log in logs:
                assert log["total_logged_hours"] == 24.0
                assert round(sum(log["totals_hours"].values()), 2) == 24.0
                assert log["segments"][0]["start_hour"] == 0.0
                assert log["segments"][-1]["end_hour"] == 24.0

    print(
        f"PASS: {args.iterations:,} independent randomized HOS replays "
        f"(seed {args.seed})."
    )


if __name__ == "__main__":
    main()
