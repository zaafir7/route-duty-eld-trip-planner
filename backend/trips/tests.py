from datetime import datetime, timedelta, timezone
import random
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from .hos_calculator import (
    DRIVING,
    OFF_DUTY,
    ON_DUTY,
    SLEEPER,
    build_trip_plan,
    split_segments_by_day,
    validate_plan,
)
from .serializers import TripRequestSerializer
from .views import plan_trip


def make_plan(
    *,
    first_miles=110.0,
    first_hours=2.0,
    second_miles=110.0,
    second_hours=2.0,
    cycle_used=0.0,
    start=None,
):
    return build_trip_plan(
        start_time=start or datetime(2026, 7, 22, 12, tzinfo=timezone.utc),
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


class HosCalculatorTests(SimpleTestCase):
    def test_current_to_pickup_leg_is_logged_before_pickup(self):
        plan = make_plan()
        self.assertEqual(plan[0].status, DRIVING)
        self.assertIn("Current", plan[0].label)
        pickup_index = next(index for index, item in enumerate(plan) if item.event_type == "pickup")
        self.assertGreater(pickup_index, 0)
        self.assertEqual(plan[pickup_index].status, ON_DUTY)

    def test_scheduled_driving_uses_route_service_duration(self):
        plan = make_plan(first_hours=1.75, second_hours=3.25)
        total = sum(item.duration_hours for item in plan if item.status == DRIVING)
        self.assertAlmostEqual(total, 5.0, places=6)

    def test_break_is_added_after_eight_cumulative_driving_hours(self):
        plan = make_plan(
            first_miles=0,
            first_hours=0,
            second_miles=495,
            second_hours=9,
        )
        breaks = [item for item in plan if item.event_type == "break"]
        self.assertEqual(len(breaks), 1)
        pickup = next(item for item in plan if item.event_type == "pickup")
        driving_since_pickup = sum(
            item.duration_hours
            for item in plan
            if item.status == DRIVING and pickup.end <= item.end <= breaks[0].start
        )
        self.assertAlmostEqual(driving_since_pickup, 8.0, places=6)
        self.assertAlmostEqual(breaks[0].duration_hours, 0.5, places=6)

    def test_pickup_itself_satisfies_break_before_more_driving(self):
        plan = make_plan(first_miles=440, first_hours=8, second_miles=25, second_hours=0.5)
        pickup_index = next(index for index, item in enumerate(plan) if item.event_type == "pickup")
        next_drive_index = next(
            index for index, item in enumerate(plan) if index > pickup_index and item.status == DRIVING
        )
        intervening = plan[pickup_index + 1 : next_drive_index]
        self.assertFalse(any(item.event_type == "break" for item in intervening))

    def test_ten_hour_rest_is_added_after_eleven_driving_hours(self):
        plan = make_plan(first_miles=0, first_hours=0, second_miles=825, second_hours=15)
        rests = [item for item in plan if item.event_type == "rest"]
        self.assertTrue(rests)
        self.assertTrue(all(item.status == SLEEPER for item in rests))
        self.assertTrue(all(abs(item.duration_hours - 10.0) < 0.001 for item in rests))

    def test_fuel_stop_is_added_at_exact_final_thousand_mile_threshold(self):
        plan = make_plan(first_miles=0, first_hours=0, second_miles=1000, second_hours=10)
        fuel_stops = [item for item in plan if item.event_type == "fuel"]
        self.assertEqual(len(fuel_stops), 1)
        self.assertAlmostEqual(fuel_stops[0].start_mile, 1000.0, places=1)
        self.assertEqual(fuel_stops[0].status, ON_DUTY)
        dropoff = next(item for item in plan if item.event_type == "dropoff")
        self.assertLess(fuel_stops[0].end, dropoff.end)

    def test_non_driving_dropoff_may_finish_after_cycle_reaches_70(self):
        plan = make_plan(
            first_miles=10,
            first_hours=0.2,
            second_miles=10,
            second_hours=0.2,
            cycle_used=67.7,
        )
        dropoff = next(item for item in plan if item.event_type == "dropoff")
        self.assertGreater(dropoff.cycle_used_end, 70.0)
        self.assertFalse(any(item.event_type == "restart" for item in plan))
        self.assertEqual(validate_plan(plan, initial_cycle_used=67.7), [])

    def test_service_can_exhaust_cycle_then_restart_occurs_before_next_drive(self):
        plan = make_plan(
            first_miles=10,
            first_hours=0.2,
            second_miles=10,
            second_hours=0.2,
            cycle_used=68.8,
        )
        pickup_index = next(index for index, item in enumerate(plan) if item.event_type == "pickup")
        restart_index = next(index for index, item in enumerate(plan) if item.event_type == "restart")
        next_drive_index = next(
            index for index, item in enumerate(plan) if index > pickup_index and item.status == DRIVING
        )
        self.assertLess(pickup_index, restart_index)
        self.assertLess(restart_index, next_drive_index)
        self.assertEqual(plan[restart_index].status, OFF_DUTY)
        self.assertAlmostEqual(plan[restart_index].duration_hours, 34.0, places=6)

    def test_generated_long_plan_passes_independent_validation(self):
        plan = make_plan(
            first_miles=700,
            first_hours=12.2,
            second_miles=1450,
            second_hours=25.5,
            cycle_used=18,
        )
        self.assertEqual(validate_plan(plan, initial_cycle_used=18), [])

    def test_dropoff_finishes_after_14_hour_window_without_unnecessary_pre_dropoff_rest(self):
        # Multiple threshold fuel stops create a long duty window while total
        # driving remains at the legal 11-hour limit. Non-driving drop-off work
        # may still finish after the 14th hour.
        plan = make_plan(
            first_miles=0,
            first_hours=0,
            second_miles=5000,
            second_hours=11,
        )
        dropoff_index = next(index for index, item in enumerate(plan) if item.event_type == "dropoff")
        dropoff = plan[dropoff_index]
        duty_start = next(item.start for item in plan if item.status in (DRIVING, ON_DUTY))
        self.assertGreater((dropoff.end - duty_start).total_seconds() / 3600, 14.0)
        self.assertNotEqual(plan[dropoff_index - 1].event_type, "rest")
        self.assertEqual(validate_plan(plan, initial_cycle_used=0), [])

    def test_rest_is_inserted_before_driving_after_service_ends_past_14_hours(self):
        plan = make_plan(
            first_miles=5000,
            first_hours=11,
            second_miles=55,
            second_hours=1,
        )
        pickup_index = next(index for index, item in enumerate(plan) if item.event_type == "pickup")
        next_drive_index = next(
            index for index, item in enumerate(plan) if index > pickup_index and item.status == DRIVING
        )
        between = plan[pickup_index + 1 : next_drive_index]
        self.assertTrue(any(item.event_type == "rest" for item in between))
        self.assertEqual(validate_plan(plan, initial_cycle_used=0), [])

    def test_no_restart_is_appended_when_trip_finishes_at_cycle_limit(self):
        plan = make_plan(
            first_miles=5,
            first_hours=0.1,
            second_miles=5,
            second_hours=0.1,
            cycle_used=67.8,
        )
        self.assertAlmostEqual(plan[-1].cycle_used_end, 70.0, places=6)
        self.assertFalse(any(item.event_type == "restart" for item in plan))
        self.assertEqual(validate_plan(plan, initial_cycle_used=67.8), [])

    def test_multiple_fuel_thresholds_are_never_more_than_1000_miles_apart(self):
        plan = make_plan(
            first_miles=500,
            first_hours=8,
            second_miles=2100,
            second_hours=34,
            cycle_used=5,
        )
        fuel_miles = [item.start_mile for item in plan if item.event_type == "fuel"]
        self.assertEqual([round(value, 1) for value in fuel_miles], [1000.0, 2000.0])
        self.assertEqual(validate_plan(plan, initial_cycle_used=5), [])

    def test_randomized_plans_pass_independent_replay(self):
        generator = random.Random(88421)
        for _ in range(250):
            first_miles = generator.uniform(0, 1500)
            second_miles = generator.uniform(0, 3500)
            first_hours = 0.0 if first_miles < 0.001 else generator.uniform(
                max(0.02, first_miles / 85), max(0.03, first_miles / 35)
            )
            second_hours = 0.0 if second_miles < 0.001 else generator.uniform(
                max(0.02, second_miles / 85), max(0.03, second_miles / 35)
            )
            cycle_used = generator.uniform(0, 70)
            plan = make_plan(
                first_miles=first_miles,
                first_hours=first_hours,
                second_miles=second_miles,
                second_hours=second_hours,
                cycle_used=cycle_used,
            )
            self.assertEqual(validate_plan(plan, initial_cycle_used=cycle_used), [])
            self.assertAlmostEqual(
                sum(item.miles for item in plan if item.status == DRIVING),
                first_miles + second_miles,
                places=3,
            )
            self.assertAlmostEqual(
                sum(item.duration_hours for item in plan if item.status == DRIVING),
                first_hours + second_hours,
                places=5,
            )

    def test_continuing_rest_is_not_duplicated_as_midnight_status_change(self):
        plan = make_plan(
            first_miles=0,
            first_hours=0,
            second_miles=825,
            second_hours=15,
            start=datetime(2026, 7, 22, 4, 0, tzinfo=timezone.utc),
        )
        logs = split_segments_by_day(plan, {}, display_tz=timezone.utc, initial_cycle_used=0)
        self.assertGreaterEqual(len(logs), 2)
        midnight_rest_remarks = [
            remark
            for log in logs
            for remark in log["remarks"]
            if remark["time"] == "00:00" and remark["label"] == "Required 10-hour rest"
        ]
        self.assertEqual(midnight_rest_remarks, [])
        self.assertEqual(logs[-1]["remarks"][-1]["label"], "Trip complete — off duty")

    def test_daily_logs_use_fixed_home_terminal_time_and_total_24_hours(self):
        display_tz = timezone(timedelta(hours=-5), name="America/Chicago")
        start_utc = datetime(2026, 7, 23, 4, 30, tzinfo=timezone.utc)  # 23:30 previous day
        plan = make_plan(
            first_miles=55,
            first_hours=1,
            second_miles=55,
            second_hours=1,
            start=start_utc,
        )
        logs = split_segments_by_day(
            plan,
            {
                "driver_name": "Driver",
                "carrier_name": "Carrier",
                "main_office_address": "Office",
                "home_terminal_address": "Terminal",
                "vehicle_numbers": "Truck",
                "shipping_document_number": "Ship",
            },
            display_tz=display_tz,
            initial_cycle_used=0,
        )
        self.assertGreaterEqual(len(logs), 2)
        self.assertEqual(logs[0]["date"], "2026-07-22")
        for log in logs:
            self.assertAlmostEqual(log["total_logged_hours"], 24.0, places=6)
            self.assertAlmostEqual(sum(log["totals_hours"].values()), 24.0, places=6)
            self.assertEqual(log["segments"][0]["start_hour"], 0.0)
            self.assertEqual(log["segments"][-1]["end_hour"], 24.0)

        # A status continuing through midnight is not incorrectly recorded as
        # a new change at 00:00, while the final transition to off duty is.
        all_remarks = [remark for log in logs for remark in log["remarks"]]
        self.assertFalse(
            any(
                remark["time"] == "00:00" and remark["label"] == "Required 10-hour rest"
                for remark in all_remarks
            )
        )
        self.assertEqual(all_remarks[-1]["label"], "Trip complete — off duty")


class SerializerTests(SimpleTestCase):

    def test_non_finite_cycle_value_is_rejected(self):
        serializer = TripRequestSerializer(
            data={
                "current_location": "Dallas, TX",
                "pickup_location": "Austin, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used": float("nan"),
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("current_cycle_used", serializer.errors)

    def test_invalid_time_zone_is_rejected(self):
        serializer = TripRequestSerializer(
            data={
                "current_location": "Dallas, TX",
                "pickup_location": "Austin, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used": 0,
                "home_terminal_timezone": "Not/AZone",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("home_terminal_timezone", serializer.errors)


    def test_nonexistent_daylight_saving_local_time_is_rejected(self):
        serializer = TripRequestSerializer(
            data={
                "current_location": "Dallas, TX",
                "pickup_location": "Austin, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used": 0,
                "start_time_local": "2026-03-08T02:30",
                "home_terminal_timezone": "America/Chicago",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("start_time_local", serializer.errors)

    def test_ambiguous_daylight_saving_local_time_is_rejected(self):
        serializer = TripRequestSerializer(
            data={
                "current_location": "Dallas, TX",
                "pickup_location": "Austin, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used": 0,
                "start_time_local": "2026-11-01T01:30",
                "home_terminal_timezone": "America/Chicago",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("start_time_local", serializer.errors)


class ApiTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    @patch("trips.views.reverse_geocode", return_value="Route City, TX")
    @patch("trips.views.route_between")
    @patch("trips.views.geocode")
    def test_plan_trip_api_returns_route_logs_and_validated_schedule(
        self,
        geocode_mock,
        route_mock,
        _reverse_mock,
    ):
        geocode_mock.side_effect = [
            {"name": "Dallas, TX", "display_name": "Dallas", "short_name": "Dallas, TX", "lat": 32.7, "lon": -96.8},
            {"name": "Austin, TX", "display_name": "Austin", "short_name": "Austin, TX", "lat": 30.2, "lon": -97.7},
            {"name": "Houston, TX", "display_name": "Houston", "short_name": "Houston, TX", "lat": 29.7, "lon": -95.3},
        ]
        route_mock.return_value = {
            "miles": 300.0,
            "driving_hours": 5.5,
            "map_duration_hours": 5.5,
            "geometry": [[-96.8, 32.7], [-97.7, 30.2], [-95.3, 29.7]],
            "legs": [
                {
                    "index": 0,
                    "from_name": "Dallas, TX",
                    "to_name": "Austin, TX",
                    "miles": 190.0,
                    "driving_hours": 3.2,
                    "map_duration_hours": 3.2,
                    "instructions": [],
                },
                {
                    "index": 1,
                    "from_name": "Austin, TX",
                    "to_name": "Houston, TX",
                    "miles": 110.0,
                    "driving_hours": 2.3,
                    "map_duration_hours": 2.3,
                    "instructions": [],
                },
            ],
        }
        request = self.factory.post(
            "/api/plan-trip/",
            {
                "current_location": "Dallas, TX",
                "pickup_location": "Austin, TX",
                "dropoff_location": "Houston, TX",
                "current_cycle_used": 12,
                "start_time_local": "2026-07-22T08:00",
                "home_terminal_timezone": "America/Chicago",
            },
            format="json",
        )
        response = plan_trip(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["validation"]["passed"])
        self.assertAlmostEqual(response.data["trip_summary"]["total_driving_hours"], 5.5, places=2)
        self.assertTrue(response.data["daily_logs"])
        self.assertEqual(response.data["time_basis"]["iana_name"], "America/Chicago")
        self.assertEqual(response.data["itinerary"][0]["location"], "Dallas, TX")

    @patch("trips.views.route_between")
    @patch("trips.views.geocode")
    def test_plan_trip_api_rejects_route_without_geometry(self, geocode_mock, route_mock):
        geocode_mock.side_effect = [
            {"name": "A", "display_name": "A", "short_name": "A, TX", "lat": 1.0, "lon": 1.0},
            {"name": "B", "display_name": "B", "short_name": "B, TX", "lat": 2.0, "lon": 2.0},
            {"name": "C", "display_name": "C", "short_name": "C, TX", "lat": 3.0, "lon": 3.0},
        ]
        route_mock.return_value = {"legs": [{}, {}], "geometry": []}
        request = self.factory.post(
            "/api/plan-trip/",
            {
                "current_location": "A, TX",
                "pickup_location": "B, TX",
                "dropoff_location": "C, TX",
                "current_cycle_used": 0,
                "home_terminal_timezone": "UTC",
            },
            format="json",
        )
        response = plan_trip(request)
        self.assertEqual(response.status_code, 400)

