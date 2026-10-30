from django.test import SimpleTestCase

from meetings.ai import build_summary_messages, parse_summary_response


class SummarizeMeetingTests(SimpleTestCase):
    def test_prompt_contains_transcript_and_officer_notes(self):
        messages = build_summary_messages("The budget passed.", "Send the approved budget.")
        self.assertIn("The budget passed.", messages[1]["content"])
        self.assertIn("Send the approved budget.", messages[1]["content"])

    def test_normalizes_action_item_prefix(self):
        result = parse_summary_response('{"summary": "Discussion", "action_items": ["Follow up"]}')
        self.assertEqual(result.action_items, ["Action: Follow up"])

    def test_rejects_empty_inputs(self):
        with self.assertRaisesMessage(ValueError, "empty transcript"):
            build_summary_messages("  ", " ")

    def test_rejects_malformed_response(self):
        with self.assertRaisesMessage(RuntimeError, "valid summary string"):
            parse_summary_response('{"summary": "", "action_items": []}')
