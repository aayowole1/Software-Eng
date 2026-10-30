"""OpenAI-powered meeting summarization and action-item extraction."""

import json
import os
from dataclasses import dataclass, field


@dataclass
class MeetingSummary:
    summary: str
    action_items: list[str] = field(default_factory=list)


def summarize_meeting(notes: str) -> MeetingSummary:
    """Summarize notes with OpenAI and reject malformed provider responses."""
    if not notes.strip():
        raise ValueError("Cannot summarize an empty transcript.")

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    try:
        from openai import OpenAI, OpenAIError

        response = OpenAI(
            api_key=api_key,
            timeout=30.0,
            max_retries=2,
        ).chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You summarize meeting transcripts. Return only valid JSON "
                        'with exactly two fields: "summary" (a concise string describing '
                        'what was discussed) and "action_items" (an array of strings). '
                        'Each action item must start with exactly "Action:", "TODO:", '
                        'or "- [ ]". Do not invent actions unsupported by the transcript.'
                    ),
                },
                {"role": "user", "content": f"Transcript:\n\n{notes}"},
            ],
        )
        content = response.choices[0].message.content
    except ImportError as error:
        raise RuntimeError(f"OpenAI summarization is unavailable: {error}") from error
    except (OpenAIError, OSError, TimeoutError) as error:
        raise RuntimeError(f"OpenAI summarization failed: {error}") from error

    if not content:
        raise RuntimeError("OpenAI returned an empty summarization response.")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise RuntimeError("OpenAI returned invalid JSON for the meeting summary.") from error

    if not isinstance(payload, dict):
        raise RuntimeError("OpenAI summary must be a JSON object.")
    summary = payload.get("summary")
    action_items = payload.get("action_items")
    if not isinstance(summary, str) or not summary.strip():
        raise RuntimeError("OpenAI summary is missing a valid summary string.")
    if not isinstance(action_items, list) or not all(
        isinstance(item, str) and item.strip() for item in action_items
    ):
        raise RuntimeError("OpenAI summary contains invalid action items.")

    normalized_items = []
    for item in action_items:
        item = item.strip()
        if not item.startswith(("Action:", "TODO:", "- [ ]")):
            item = f"Action: {item}"
        normalized_items.append(item)
    return MeetingSummary(summary=summary.strip(), action_items=normalized_items)
