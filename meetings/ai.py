"""
Meeting-note summarization and action-item extraction (FR-06).

PLACEHOLDER: this is a simple rule-based stand-in so the review workflow can
be built and tested without an AI provider, API key, or budget. It should be
replaced by a real language-model call (WBS 1.9, AI/quality lead) and
evaluated with DeepEval against the labeled meeting-note set described in
the proposal (precision >= 0.85, recall >= 0.80).

Whatever replaces it must keep the same signature:
    summarize_meeting(notes: str) -> MeetingSummary
"""

import re
from dataclasses import dataclass, field

# Lines like "Action: ...", "TODO - ...", "- [ ] ...", "AI: ..." are action items.
ACTION_PATTERN = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:\[\s?\]\s*|(?:action(?:\s*item)?|todo|ai)\s*[:\-]\s*)(?P<text>.+)$",
    re.IGNORECASE,
)
SUMMARY_SENTENCES = 3


@dataclass
class MeetingSummary:
    summary: str
    action_items: list[str] = field(default_factory=list)


def summarize_meeting(notes):
    action_items = []
    other_lines = []
    for line in notes.splitlines():
        match = ACTION_PATTERN.match(line)
        if match:
            action_items.append(match.group("text").strip())
        elif line.strip():
            other_lines.append(line.strip(" -*•\t"))

    text = " ".join(other_lines)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    summary = " ".join(sentences[:SUMMARY_SENTENCES])
    return MeetingSummary(summary=summary, action_items=action_items)
