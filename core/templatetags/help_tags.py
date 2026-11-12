"""Render the help guides' **bold** markers safely (SCRUM-50)."""

import re
from datetime import datetime

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils import timezone

register = template.Library()


@register.filter
def help_text(value):
    """Escape the text, then turn **phrase** into <strong>phrase</strong>."""
    return mark_safe(re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escape(value)))


@register.filter
def human_datetime(value):
    """Format ISO timestamps for readable, locale-aware display."""
    if not value:
        return ""
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return value
    if timezone.is_naive(moment):
        moment = moment.replace(tzinfo=timezone.utc)
    return timezone.localtime(moment).strftime("%b %-d, %Y, %-I:%M %p")
