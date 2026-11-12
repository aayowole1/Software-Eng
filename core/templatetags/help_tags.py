"""Render the help guides' **bold** markers safely (SCRUM-50)."""

import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def help_text(value):
    """Escape the text, then turn **phrase** into <strong>phrase</strong>."""
    return mark_safe(re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escape(value)))
