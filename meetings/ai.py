"""OpenRouter-powered meeting summarization and action-item extraction."""

import json
import os
from dataclasses import dataclass, field


@dataclass
class MeetingSummary:
    summary: str
    action_items: list[str] = field(default_factory=list)


def build_summary_messages(transcript: str, officer_notes: str = "") -> list[dict[str, str]]:
    """Build the provider-independent prompt for a meeting summary."""
    transcript = transcript.strip()
    officer_notes = officer_notes.strip()
    if not transcript and not officer_notes:
        raise ValueError("Cannot summarize an empty transcript and empty officer notes.")
    return [
        {
            "role": "system",
            "content": (
                "You summarize meeting transcripts and officer notes. Return only "
                'valid JSON with exactly two fields: "summary" (a concise string '
                'describing what was discussed) and "action_items" (an array of '
                "strings). Each action item must start with exactly "
                '"Action:", "TODO:", or "- [ ]". Do not invent actions unsupported '
                "by the transcript or officer notes."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Transcript:\n\n{transcript or '(No transcript provided.)'}\n\n"
                f"Officer notes:\n\n{officer_notes or '(No officer notes provided.)'}"
            ),
        },
    ]


def parse_summary_response(content: str | None) -> MeetingSummary:
    """Validate and normalize a provider response without making a network call."""
    if not content:
        raise RuntimeError("OpenRouter returned an empty summarization response.")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise RuntimeError("OpenRouter returned invalid JSON for the meeting summary.") from error

    if not isinstance(payload, dict):
        raise RuntimeError("OpenRouter summary must be a JSON object.")
    summary = payload.get("summary")
    action_items = payload.get("action_items")
    if not isinstance(summary, str) or not summary.strip():
        raise RuntimeError("OpenRouter summary is missing a valid summary string.")
    if not isinstance(action_items, list) or not all(
        isinstance(item, str) and item.strip() for item in action_items
    ):
        raise RuntimeError("OpenRouter summary contains invalid action items.")

    normalized_items = []
    for item in action_items:
        item = item.strip()
        if not item.startswith(("Action:", "TODO:", "- [ ]")):
            item = f"Action: {item}"
        normalized_items.append(item)
    return MeetingSummary(summary=summary.strip(), action_items=normalized_items)


def summarize_meeting(transcript: str, officer_notes: str = "") -> MeetingSummary:
    """Send a meeting transcript and officer notes to OpenRouter."""
    messages = build_summary_messages(transcript, officer_notes)

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured.")

    try:
        from openai import OpenAI, OpenAIError

        response = OpenAI(
            api_key=api_key,
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            default_headers={
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", ""),
                "X-Title": os.getenv("OPENROUTER_APP_NAME", "OrgFlow"),
            },
            timeout=30.0,
            max_retries=2,
        ).chat.completions.create(
            model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=messages,
        )
        content = response.choices[0].message.content
    except ImportError as error:
        raise RuntimeError(f"OpenRouter summarization is unavailable: {error}") from error
    except (OpenAIError, OSError, TimeoutError) as error:
        raise RuntimeError(f"OpenRouter summarization failed: {error}") from error

    return parse_summary_response(content)
