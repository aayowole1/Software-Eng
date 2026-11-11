"""Small helpers for reading settings from environment variables."""

import os


def env_text(name, default):
    """Return the variable's value, or `default` when it is unset or blank.

    A copied `.env.example` sets variables to empty strings (`ORG_NAME=`), so
    blank values are treated the same as missing ones.
    """
    value = os.getenv(name, "").strip()
    return value or default


def env_list(name, default, separator="|"):
    """Split the variable on `separator`, dropping blank items.

    Falls back to `default` (a string in the same format) when the variable is
    unset, blank, or contains no non-blank items.
    """
    items = [item.strip() for item in env_text(name, "").split(separator) if item.strip()]
    return items or [item.strip() for item in default.split(separator) if item.strip()]
