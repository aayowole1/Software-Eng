"""Readiness is database-backed, bounded, read-only and safe to publish."""

from unittest.mock import patch

from django.db import OperationalError
from django.test import SimpleTestCase
from django.urls import reverse
from pymongo.errors import ServerSelectionTimeoutError


class ReadinessTests(SimpleTestCase):
    @patch("core.views.connections")
    def test_get_pings_database_and_prevents_cached_ready_response(self, connections):
        response = self.client.get(reverse("core:readiness"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready"})
        connections["default"].get_database().command.assert_called_once_with("ping")
        self.assertIn("no-store", response.headers["Cache-Control"])

    @patch("core.views.connections")
    def test_database_failure_returns_generic_unavailable_without_details(self, connections):
        for failure in (OperationalError("private database details"), ServerSelectionTimeoutError("private connection details")):
            with self.subTest(error=type(failure).__name__):
                connections["default"].get_database.side_effect = failure
                response = self.client.get(reverse("core:readiness"))
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"status": "unavailable"})
                self.assertNotIn("private", response.content.decode())

    @patch("core.views.connections")
    def test_post_is_rejected_without_checking_database(self, connections):
        self.assertEqual(self.client.post(reverse("core:readiness")).status_code, 405)
        connections["default"].get_database.assert_not_called()

    @patch("core.views.connections")
    def test_liveness_stays_independent_of_database(self, connections):
        connections["default"].get_database.side_effect = OperationalError("Database unavailable")
        response = self.client.get(reverse("core:health"))
        self.assertEqual((response.status_code, response.json()), (200, {"status": "ok"}))
        connections["default"].get_database.assert_not_called()
