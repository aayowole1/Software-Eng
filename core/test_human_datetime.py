from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .templatetags.help_tags import human_datetime


@override_settings(TIME_ZONE="America/Chicago", LANGUAGE_CODE="en-us")
class HumanDatetimeTests(SimpleTestCase):
    def test_aware_iso_value_uses_organization_timezone(self):
        self.assertEqual(human_datetime("2026-11-12T15:05:00+00:00"), "Nov 12, 2026, 9:05 AM")

    def test_naive_iso_value_is_treated_as_utc(self):
        self.assertEqual(human_datetime("2026-11-12T15:05:00"), "Nov 12, 2026, 9:05 AM")

    def test_datetime_object_and_midnight(self):
        value = datetime(2026, 11, 12, 6, 7, tzinfo=dt_timezone.utc)
        self.assertEqual(human_datetime(value), "Nov 12, 2026, 12:07 AM")

    def test_noon_and_single_digit_day(self):
        self.assertEqual(human_datetime("2026-11-03T18:09:00+00:00"), "Nov 3, 2026, 12:09 PM")

    def test_invalid_value_is_preserved(self):
        self.assertEqual(human_datetime("unknown date"), "unknown date")

    def test_empty_value_stays_empty(self):
        self.assertEqual(human_datetime(None), "")
        self.assertEqual(human_datetime(""), "")

    def test_windows_unsupported_strftime_flags_are_not_used(self):
        class WindowsDatetime(datetime):
            def strftime(self, format):
                if "%-" in format:
                    raise ValueError("Invalid format string")
                return super().strftime(format)

        local = WindowsDatetime(2026, 11, 12, 9, 5, tzinfo=dt_timezone.utc)
        with patch("core.templatetags.help_tags.timezone.localtime", return_value=local):
            self.assertEqual(human_datetime("2026-11-12T15:05:00+00:00"), "Nov 12, 2026, 9:05 AM")
