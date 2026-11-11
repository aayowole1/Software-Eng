"""Tests for the shared CSV formula-escaping helper."""

from django.test import SimpleTestCase

from core.csv_safe import escape_csv_cell


class EscapeCsvCellTests(SimpleTestCase):
    def test_formula_triggers_are_prefixed(self):
        for value in ["=SUM(A1)", "+1", "-2", "@cmd", "\tTAB", "\rCR"]:
            with self.subTest(value=value):
                self.assertEqual(escape_csv_cell(value), "'" + value)

    def test_safe_values_are_unchanged(self):
        for value in ["alice", "a=b", "2026-11-03", "Member", ""]:
            with self.subTest(value=value):
                self.assertEqual(escape_csv_cell(value), value)

    def test_none_and_numbers_become_text(self):
        self.assertEqual(escape_csv_cell(None), "")
        self.assertEqual(escape_csv_cell(42), "42")
        self.assertEqual(escape_csv_cell(-5), "'-5")
