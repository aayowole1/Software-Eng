"""Write the user and admin guide to docs/ from core/help_content.py (SCRUM-50)."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core.help_content import render_markdown

DOC_PATH = Path(settings.BASE_DIR) / "docs" / "user-and-admin-guide.md"


class Command(BaseCommand):
    help = "Regenerate docs/user-and-admin-guide.md from the in-app Help guides."

    def handle(self, *args, **options):
        DOC_PATH.write_text(render_markdown(), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote {DOC_PATH.relative_to(settings.BASE_DIR)}"))
