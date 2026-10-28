"""Unit tests for meetings/ai.py — summarize_meeting().

These complement the integration tests in tests.py with more targeted checks
on action-item extraction patterns, summary limits, and edge cases.
"""

from django.test import SimpleTestCase

from .ai import SUMMARY_SENTENCES, MeetingSummary, summarize_meeting


class SummarizeMeetingTests(SimpleTestCase):
    """Direct unit tests for summarize_meeting()."""

    # ---- return type ----

    def test_returns_meeting_summary_instance(self):
        result = summarize_meeting("Hello world.")
        self.assertIsInstance(result, MeetingSummary)

    def test_summary_field_is_string(self):
        result = summarize_meeting("One sentence.")
        self.assertIsInstance(result.summary, str)

    def test_action_items_field_is_list(self):
        result = summarize_meeting("")
        self.assertIsInstance(result.action_items, list)

    # ---- empty / whitespace input ----

    def test_empty_notes_produces_empty_summary_and_no_actions(self):
        result = summarize_meeting("")
        self.assertEqual(result.summary, "")
        self.assertEqual(result.action_items, [])

    def test_whitespace_only_notes_produces_empty_summary(self):
        result = summarize_meeting("   \n\n   ")
        self.assertEqual(result.summary, "")
        self.assertEqual(result.action_items, [])

    # ---- action-item extraction ----

    def test_action_prefix_is_extracted(self):
        result = summarize_meeting("Action: Buy coffee filters")
        self.assertIn("Buy coffee filters", result.action_items)

    def test_todo_prefix_is_extracted(self):
        result = summarize_meeting("TODO: Send the agenda")
        self.assertIn("Send the agenda", result.action_items)

    def test_todo_dash_prefix_is_extracted(self):
        result = summarize_meeting("TODO - Draft the proposal")
        self.assertIn("Draft the proposal", result.action_items)

    def test_checkbox_prefix_is_extracted(self):
        result = summarize_meeting("- [ ] Book the room")
        self.assertIn("Book the room", result.action_items)

    def test_ai_prefix_is_extracted(self):
        result = summarize_meeting("AI: Generate the meeting summary")
        self.assertIn("Generate the meeting summary", result.action_items)

    def test_action_item_prefix_is_extracted(self):
        result = summarize_meeting("Action Item: Update the roadmap")
        self.assertIn("Update the roadmap", result.action_items)

    def test_action_items_are_case_insensitive(self):
        result = summarize_meeting("action: lower case item")
        self.assertIn("lower case item", result.action_items)

    def test_extracted_text_is_stripped(self):
        result = summarize_meeting("Action:   Trim whitespace   ")
        self.assertIn("Trim whitespace", result.action_items)

    def test_ordinary_lines_are_not_extracted_as_actions(self):
        result = summarize_meeting("We discussed the budget.")
        self.assertEqual(result.action_items, [])

    def test_multiple_action_items_preserve_order(self):
        notes = (
            "Action: First task\n"
            "Action: Second task\n"
            "Action: Third task\n"
        )
        result = summarize_meeting(notes)
        self.assertEqual(result.action_items, ["First task", "Second task", "Third task"])

    # ---- summary construction ----

    def test_summary_excludes_action_item_lines(self):
        notes = "We had a great meeting.\nAction: Do something."
        result = summarize_meeting(notes)
        self.assertNotIn("Do something", result.summary)
        self.assertIn("great meeting", result.summary)

    def test_summary_is_limited_to_three_sentences(self):
        sentences = [f"Sentence {i}." for i in range(10)]
        result = summarize_meeting(" ".join(sentences))
        summary_sentences = [s for s in result.summary.split(". ") if s]
        self.assertLessEqual(len(summary_sentences), SUMMARY_SENTENCES)

    def test_summary_from_fewer_than_three_sentences(self):
        result = summarize_meeting("Only one sentence.")
        self.assertIn("Only one sentence", result.summary)

    def test_summary_strips_bullet_and_dash_prefixes(self):
        notes = "- A bullet point.\n* Another point."
        result = summarize_meeting(notes)
        self.assertNotIn("-", result.summary)

    def test_notes_with_only_action_items_produces_empty_summary(self):
        notes = "Action: Do this.\nTODO: Do that."
        result = summarize_meeting(notes)
        self.assertEqual(result.summary, "")
        self.assertEqual(len(result.action_items), 2)

    # ---- mixed content ----

    def test_mixed_notes_produce_correct_summary_and_actions(self):
        notes = (
            "The team met to plan the conference.\n"
            "We agreed on the venue.\n"
            "Action: Book the venue by Friday\n"
            "TODO - Send invitations next week\n"
            "Budget discussion will continue next meeting.\n"
        )
        result = summarize_meeting(notes)
        self.assertIn("conference", result.summary)
        self.assertNotIn("Book the venue", result.summary)
        self.assertIn("Book the venue by Friday", result.action_items)
        self.assertIn("Send invitations next week", result.action_items)
