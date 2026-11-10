"""Check that benchmark evidence cannot count failures or 3s responses as passes."""
import unittest

from deploy.benchmark_pages import summary


class BenchmarkSummaryTests(unittest.TestCase):
    def test_empty_sample_is_not_a_pass(self):
        self.assertFalse(summary([])["meets_95_percent_under_3s"])

    def test_exactly_three_seconds_does_not_count_as_under_three(self):
        result = summary([{"seconds": 3.0, "ok": True}])
        self.assertEqual(result["successful_under_3s_percent"], 0)
        self.assertFalse(result["meets_95_percent_under_3s"])

    def test_fast_http_errors_are_not_successful_requests(self):
        result = summary([{"seconds": .01, "ok": False} for _ in range(20)])
        self.assertEqual(result["errors"], 20)
        self.assertEqual(result["successful_under_3s_percent"], 0)

    def test_nineteen_of_twenty_successful_fast_requests_meets_95_percent(self):
        result = summary([{"seconds": 1, "ok": True}] * 19 + [{"seconds": 4, "ok": True}])
        self.assertEqual(result["successful_under_3s_percent"], 95)
        self.assertEqual(result["p95_seconds"], 1)
        self.assertTrue(result["meets_95_percent_under_3s"])

    def test_eighteen_of_twenty_fails_even_when_every_http_response_succeeds(self):
        result = summary([{"seconds": 1, "ok": True}] * 18 + [{"seconds": 4, "ok": True}] * 2)
        self.assertEqual(result["successful_under_3s_percent"], 90)
        self.assertEqual(result["errors"], 0)
        self.assertFalse(result["meets_95_percent_under_3s"])


if __name__ == "__main__":
    unittest.main()
