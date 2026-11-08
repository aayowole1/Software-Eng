"""Unit tests for meetings/ai.py — summarize_meeting() with OpenRouter.

The OpenAI client is replaced with a fake, so these run without an API key,
network access or cost. They check the request we send and how provider
responses are validated and normalized.
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from openai import OpenAIError

from .ai import MeetingSummary, build_summary_messages, summarize_meeting


def provider_returning(content):
    """A fake OpenRouter-compatible OpenAI client."""
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    return MagicMock(return_value=client), client


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key", "OPENROUTER_MODEL": "openrouter/free"})
class SummarizeMeetingTests(SimpleTestCase):

    def test_blank_officer_notes_are_omitted_from_prompt(self):
        messages = build_summary_messages("Transcript text", "")
        self.assertNotIn("Officer notes", messages[-1]["content"])

    def summarize(self, content, notes="We met. Action: Book room"):
        fake_class, client = provider_returning(content)
        with patch("openai.OpenAI", fake_class):
            result = summarize_meeting(notes)
        return result, fake_class, client

    def payload(self, summary="We planned the event.", items=("Action: Book room",)):
        return json.dumps({"summary": summary, "action_items": list(items)})

    # ---- successful responses ----

    def test_returns_meeting_summary(self):
        result, _, _ = self.summarize(self.payload())
        self.assertIsInstance(result, MeetingSummary)
        self.assertEqual(result.summary, "We planned the event.")
        self.assertEqual(result.action_items, ["Action: Book room"])

    def test_summary_and_items_are_trimmed(self):
        result, _, _ = self.summarize(self.payload("  Summary.  ", ["  TODO: Email sponsors  "]))
        self.assertEqual(result.summary, "Summary.")
        self.assertEqual(result.action_items, ["TODO: Email sponsors"])

    def test_items_keep_their_allowed_prefix(self):
        items = ["Action: One", "TODO: Two", "- [ ] Three"]
        result, _, _ = self.summarize(self.payload(items=items))
        self.assertEqual(result.action_items, items)

    def test_items_without_a_prefix_get_action_prefix(self):
        result, _, _ = self.summarize(self.payload(items=["Book the atrium"]))
        self.assertEqual(result.action_items, ["Action: Book the atrium"])

    def test_no_action_items_is_allowed(self):
        result, _, _ = self.summarize(self.payload(items=[]))
        self.assertEqual(result.action_items, [])

    # ---- request sent to the provider ----

    def test_sends_notes_with_json_format_and_default_model(self):
        _, fake_class, client = self.summarize(self.payload(), notes="Budget talk")
        fake_class.assert_called_once()
        self.assertEqual(fake_class.call_args.kwargs["api_key"], "test-key")
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "openrouter/free")
        self.assertEqual(request["response_format"], {"type": "json_object"})
        self.assertIn("Budget talk", request["messages"][-1]["content"])
        self.assertEqual(fake_class.call_args.kwargs["timeout"], 30.0)
        self.assertEqual(fake_class.call_args.kwargs["max_retries"], 2)

    @patch.dict(os.environ, {"OPENROUTER_MODEL": "gpt-test"})
    def test_model_can_be_overridden(self):
        _, _, client = self.summarize(self.payload())
        self.assertEqual(client.chat.completions.create.call_args.kwargs["model"], "gpt-test")

    # ---- inputs rejected before calling the provider ----

    def test_empty_notes_are_rejected(self):
        for notes in ["", "   \n  "]:
            with self.subTest(notes=notes), self.assertRaises(ValueError):
                summarize_meeting(notes)

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": ""})
    def test_missing_api_key_is_reported(self):
        with self.assertRaisesMessage(RuntimeError, "OPENROUTER_API_KEY is not configured"):
            summarize_meeting("Some notes")

    # ---- malformed provider responses ----

    def test_invalid_responses_raise_runtime_error(self):
        bad = {
            "empty": "",
            "not json": "Here is your summary!",
            "not an object": json.dumps(["a", "b"]),
            "missing summary": json.dumps({"action_items": []}),
            "blank summary": json.dumps({"summary": "  ", "action_items": []}),
            "items not a list": json.dumps({"summary": "S", "action_items": "Action: x"}),
            "blank item": json.dumps({"summary": "S", "action_items": ["  "]}),
            "non-string item": json.dumps({"summary": "S", "action_items": [3]}),
        }
        for label, content in bad.items():
            with self.subTest(label), self.assertRaises(RuntimeError):
                self.summarize(content)

    def test_provider_errors_become_runtime_errors(self):
        fake_class, client = provider_returning(self.payload())
        client.chat.completions.create.side_effect = OpenAIError("service unavailable")
        with patch("openai.OpenAI", fake_class), self.assertRaisesMessage(RuntimeError, "OpenRouter summarization failed"):
            summarize_meeting("Some notes")
