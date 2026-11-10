"""Synthetic unit fixtures check scoring, not human usability performance."""
import unittest
from deploy.score_usability_pilot import score


def records():
    return {"protocol": "SCRUM-83-member-login-rsvp-v1", "source_revision": "synthetic-unit-fixture",
            "environment": "unit test only", "event_title": "Fictional unit test event", "observations": [
        {"participant_id": f"P{i}", "human_confirmed": True, "observed": True,
         "elapsed_seconds": 120, "completed": True, "assisted": False}
        for i in range(1, 6)
    ]}


class PilotScoringTests(unittest.TestCase):
    def test_missing_run_metadata_cannot_pass(self):
        data = records()
        data["source_revision"] = None
        self.assertEqual(score(data)["status"], "INCOMPLETE")

    def test_empty_or_placeholder_records_are_incomplete(self):
        self.assertEqual(score({"observations": []})["status"], "INCOMPLETE")
        data = records()
        for row in data["observations"]:
            row["human_confirmed"] = None
        self.assertEqual(score(data)["status"], "INCOMPLETE")

    def test_four_of_five_at_or_below_180_seconds_pass(self):
        data = records()
        data["observations"][0]["elapsed_seconds"] = 180
        data["observations"][4]["elapsed_seconds"] = 181
        result = score(data)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["unaided_within_180_seconds"], 4)

    def test_assistance_or_noncompletion_cannot_be_counted_as_success(self):
        data = records()
        data["observations"][0]["assisted"] = True
        data["observations"][1]["completed"] = False
        self.assertEqual(score(data)["status"], "FAIL")

    def test_four_valid_people_cannot_pass_without_fifth_observation(self):
        data = records()
        data["observations"][4]["observed"] = None
        self.assertEqual(score(data)["status"], "INCOMPLETE")

    def test_duplicate_ids_cannot_pass(self):
        data = records()
        data["observations"][4]["participant_id"] = "P1"
        self.assertEqual(score(data)["status"], "INCOMPLETE")

    def test_nonhuman_records_cannot_pass(self):
        data = records()
        for row in data["observations"]:
            row["human_confirmed"] = False
        self.assertEqual(score(data)["status"], "INCOMPLETE")

    def test_invalid_times_cannot_pass(self):
        for value in (True, -1, 0, float("nan"), float("inf"), "120", None):
            with self.subTest(value=value):
                data = records()
                data["observations"][0]["elapsed_seconds"] = value
                self.assertEqual(score(data)["status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
