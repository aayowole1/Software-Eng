# Windows date rendering fix

Users/Audit pages render role-history dates through `human_datetime`. On Windows,
the Linux-only `%-d` and `%-I` strftime directives raise `ValueError: Invalid
format string`, making the Users page return500 with normal seeded history.

Use Django's date formatter after the existing organization-timezone conversion.
The display stays `Nov 12, 2026, 9:05 AM`. Naive timestamps still mean UTC;
invalid and empty values retain the previous behavior. No account, role, audit
record or permission logic changes.

Seven focused tests cover aware/naive ISO strings, datetime objects, midnight,
noon, invalid/empty values, and a platform-independent regression that rejects
Linux-only strftime flags. Existing Users/Audit/Help tests also run for this fix.
The original failure was reproduced on the local Windows practice app.
