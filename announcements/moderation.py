"""Configurable comment moderation with a local-safe default."""

import json
import os
import re
from dataclasses import dataclass
from json import JSONDecodeError


_LOCAL_FLAG_PATTERNS = (
    r"\b(?:kill|murder|threaten)\b",
    r"\b(?:go\s+die|i(?:'m| am)\s+going\s+to\s+hurt)\b",
    r"\b(?:hate|stupid|idiot)\b",
)


@dataclass(frozen=True)
class ModerationResult:
    flagged: bool
    reason: str
    provider: str


def _local_moderate(content: str) -> ModerationResult:
    if any(re.search(pattern, content, re.IGNORECASE) for pattern in _LOCAL_FLAG_PATTERNS):
        return ModerationResult(True, "Local safety check requires officer review.", "local")
    return ModerationResult(False, "", "local")


def _openrouter_moderate(content: str) -> ModerationResult:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return ModerationResult(True, "OpenRouter moderation is not configured; officer review required.", "openrouter")
    try:
        from openai import OpenAI, OpenAIError
    except ImportError:
        return ModerationResult(True, "Automated moderation was unavailable; officer review required.", "openrouter")
    try:
        response = OpenAI(
            api_key=api_key,
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            default_headers={
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", ""),
                "X-Title": os.getenv("OPENROUTER_APP_NAME", "OrgFlow"),
            },
            timeout=15.0,
            max_retries=1,
        ).chat.completions.create(
            model=os.getenv("COMMENT_MODERATION_MODEL", os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")),
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify the user comment for threats, harassment, hateful abuse, "
                        "or targeted demeaning language. Return only JSON with boolean "
                        '"flagged" and short string "reason".'
                    ),
                },
                {"role": "user", "content": content},
            ],
        )
        payload = json.loads(response.choices[0].message.content or "")
        if not isinstance(payload, dict) or not isinstance(payload.get("flagged"), bool):
            raise ValueError("invalid moderation response")
        return ModerationResult(
            payload["flagged"],
            str(payload.get("reason", "")).strip()[:500],
            "openrouter",
        )
    except (JSONDecodeError, KeyError, TypeError, ValueError, OSError, TimeoutError, OpenAIError):
        return ModerationResult(True, "Automated moderation was unavailable; officer review required.", "openrouter")


def moderate_comment(content: str) -> ModerationResult:
    """Moderate comment text without exposing provider failures to users."""
    provider = os.getenv("COMMENT_MODERATION_PROVIDER", "local").strip().lower()
    if provider == "openrouter":
        return _openrouter_moderate(content)
    return _local_moderate(content)
