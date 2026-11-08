"""OpenRouter-powered meeting summarization and action-item extraction."""

import json
import os
from dataclasses import dataclass, field


DEFAULT_SUMMARY_MODEL = "openrouter/free"


@dataclass
class MeetingSummary:
    summary: str
    action_items: list[str] = field(default_factory=list)


def get_summary_model() -> str:
    return os.getenv("OPENROUTER_MODEL", DEFAULT_SUMMARY_MODEL)


def build_summary_messages(transcript: str, officer_notes: str = "") -> list[dict[str, str]]:
    """Build the provider-independent prompt for a meeting summary."""
    transcript = transcript.strip()
    officer_notes = officer_notes.strip()
    if not transcript and not officer_notes:
        raise ValueError("Cannot summarize an empty transcript and empty officer notes.")
    messages = [
        {
            "role": "system",
            "content": (
                "You produce a faithful meeting record from the transcript and "
                "officer notes. Return only valid JSON with exactly two fields: "
                '"summary" (a concise but complete string) and "action_items" '
                "(an array of strings). The summary must cover each material "
                "decision, proposal, constraint, date, time, amount, deadline, "
                "and unresolved condition. Preserve names, numbers, dates, "
                "negations, and conditional language exactly; do not invent facts. "
                "For every action item, preserve the responsible owner, concrete "
                "task, due date or timing, and priority when stated. Format every "
                "action item exactly as: "
                '"Action: Owner=<owner>; Task=<task>; Due=<due>; '
                'Priority=<priority>". Use "Not specified" only when the source '
                "does not state that field. Include decisions and follow-up "
                "actions, but do not turn ordinary discussion into an action."
            ),
        },
        {"role": "user", "content": f"Transcript:\n\n{transcript or '(No transcript provided.)'}"},
    ]
    if officer_notes:
        messages[1]["content"] += f"\n\nOfficer notes:\n\n{officer_notes}"
    return messages


def generate_meeting_title(transcript: str, officer_notes: str = "") -> str:
    """Generate a concise descriptive title from meeting source text."""
    source = "\n\n".join(part.strip() for part in (transcript, officer_notes) if part.strip())
    if not source:
        raise ValueError("Cannot generate a title without meeting content.")
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
            model=get_summary_model(),
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": 'Return only valid JSON with exactly one field, "title". Create a concise descriptive meeting title of no more than 80 characters. Do not invent details.',
                },
                {"role": "user", "content": source},
            ],
        )
        content = response.choices[0].message.content
    except ImportError as error:
        raise RuntimeError(f"OpenRouter title generation is unavailable: {error}") from error
    except (OpenAIError, OSError, TimeoutError) as error:
        raise RuntimeError(f"OpenRouter title generation failed: {error}") from error
    try:
        title = json.loads(content or "").get("title", "").strip()
    except (json.JSONDecodeError, AttributeError) as error:
        raise RuntimeError("OpenRouter returned invalid JSON for the meeting title.") from error
    if not title or len(title) > 80:
        raise RuntimeError("OpenRouter returned an invalid meeting title.")
    return title


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
            model=get_summary_model(),
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


def build_judge_messages(
    reference_summary: str,
    reference_action_items: list[dict],
    candidate_summary: str,
    candidate_action_items: list[str],
) -> list[dict[str, str]]:
    """Build the shared rubric prompt used to evaluate benchmark summaries."""
    return [
        {
            "role": "system",
            "content": (
                "You are a calibrated meeting-summary evaluator. Compare the "
                "candidate with the reference and score it from 1 to 5. Return "
                'only valid JSON with exactly one integer field: "score". '
                "Use this rubric: 5 = faithful, complete, and precise; 4 = "
                "mostly complete with only minor omissions or wording issues; "
                "3 = useful but has several omissions or one moderate factual "
                "error; 2 = major omissions or factual errors; 1 = unusable, "
                "mostly unsupported, or missing. Judge meaning rather than "
                "requiring identical wording. Penalize invented facts, changed "
                "numbers/dates, lost negations, and incorrect owners or deadlines. "
                "Evaluate both the prose summary and the action items."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Reference summary:\n{reference_summary}\n\n"
                f"Reference action items:\n"
                f"{json.dumps(reference_action_items, ensure_ascii=False)}\n\n"
                f"Candidate summary:\n{candidate_summary}\n\n"
                f"Candidate action items:\n"
                f"{json.dumps(candidate_action_items, ensure_ascii=False)}"
            ),
        },
    ]
