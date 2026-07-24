from __future__ import annotations

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers


class TripRequestSerializer(serializers.Serializer):
    current_location = serializers.CharField(max_length=255, trim_whitespace=True)
    pickup_location = serializers.CharField(max_length=255, trim_whitespace=True)
    dropoff_location = serializers.CharField(max_length=255, trim_whitespace=True)
    current_cycle_used = serializers.FloatField(min_value=0, max_value=70)

    start_time_local = serializers.CharField(max_length=32, required=False, allow_blank=True)
    home_terminal_timezone = serializers.CharField(max_length=80, required=False, default="UTC")

    driver_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    co_driver_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    carrier_name = serializers.CharField(max_length=160, required=False, allow_blank=True)
    main_office_address = serializers.CharField(max_length=180, required=False, allow_blank=True)
    home_terminal_address = serializers.CharField(max_length=180, required=False, allow_blank=True)
    vehicle_numbers = serializers.CharField(max_length=120, required=False, allow_blank=True)
    shipping_document_number = serializers.CharField(max_length=120, required=False, allow_blank=True)
    manifest_number = serializers.CharField(max_length=120, required=False, allow_blank=True)
    shipper_commodity = serializers.CharField(max_length=180, required=False, allow_blank=True)

    def validate_current_cycle_used(self, value: float) -> float:
        if not math.isfinite(value):
            raise serializers.ValidationError("Enter a finite number between 0 and 70.")
        return value

    def validate_home_terminal_timezone(self, value: str) -> str:
        value = value.strip() or "UTC"
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise serializers.ValidationError("Select a valid IANA time zone.") from exc
        return value

    def validate_start_time_local(self, value: str) -> str:
        value = value.strip()
        if not value:
            return value
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise serializers.ValidationError("Use a valid local date and time.") from exc
        if parsed.tzinfo is not None:
            raise serializers.ValidationError(
                "Send a local date/time without an offset; the home-terminal time zone is supplied separately."
            )
        return value

    @staticmethod
    def _valid_local_folds(naive: datetime, zone: ZoneInfo) -> list[int]:
        """Return folds that round-trip to the supplied wall-clock time.

        A nonexistent daylight-saving time has no valid fold. An ambiguous
        fall-back time has two. Rejecting both cases keeps the generated UTC
        schedule deterministic instead of silently moving the requested time.
        """

        valid: list[int] = []
        for fold in (0, 1):
            aware = naive.replace(tzinfo=zone, fold=fold)
            round_trip = aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
            if round_trip == naive:
                valid.append(fold)
        return valid

    def validate(self, attrs: dict) -> dict:
        for field in ("current_location", "pickup_location", "dropoff_location"):
            if not attrs[field].strip():
                raise serializers.ValidationError({field: "This location cannot be blank."})

        start_text = attrs.get("start_time_local", "")
        if start_text:
            naive = datetime.fromisoformat(start_text)
            zone = ZoneInfo(attrs.get("home_terminal_timezone", "UTC"))
            valid_folds = self._valid_local_folds(naive, zone)
            if not valid_folds:
                raise serializers.ValidationError(
                    {
                        "start_time_local": (
                            "That local time does not exist because of the daylight-saving clock change. "
                            "Choose a time before or after the skipped hour."
                        )
                    }
                )
            if len(valid_folds) == 2 and naive.replace(tzinfo=zone, fold=0).utcoffset() != naive.replace(
                tzinfo=zone, fold=1
            ).utcoffset():
                raise serializers.ValidationError(
                    {
                        "start_time_local": (
                            "That local time occurs twice because of the daylight-saving clock change. "
                            "Choose a time outside the repeated hour."
                        )
                    }
                )

        return attrs
