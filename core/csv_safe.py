"""Shared helpers for writing CSV downloads safely."""

# A cell starting with one of these can be run as a formula when the file is
# opened in a spreadsheet (CSV/formula injection). Tab and carriage return
# are included because some spreadsheets ignore them before a formula.
FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def escape_csv_cell(value):
    """Return the cell as text, prefixed with ' if it could start a formula."""
    text = "" if value is None else str(value)
    if text and text[0] in FORMULA_TRIGGERS:
        return "'" + text
    return text
