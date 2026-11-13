"""Every template button needs a class so the site's button style applies.

The Tailwind CDN script loads its reset after core/site.css and sets a bare
``button`` element's background to transparent. A class selector such as
``.button`` outranks that reset, so a button without a class shows up as plain
text with no background (this hid the Sign in and Create account buttons).
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BUTTON_WITHOUT_CLASS = re.compile(r"<button(?![^>]*\bclass=)[^>]*>")


class TemplateButtonClassTests(SimpleTestCase):
    def test_every_template_button_has_a_class(self):
        root = Path(settings.BASE_DIR)
        missing = []
        for template in sorted(root.glob("*/templates/**/*.html")):
            text = template.read_text(encoding="utf-8")
            for match in BUTTON_WITHOUT_CLASS.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                missing.append(f"{template.relative_to(root)}:{line}: {match.group(0)}")
        self.assertEqual(missing, [], "Add class=\"button\" (or another button class):\n" + "\n".join(missing))
