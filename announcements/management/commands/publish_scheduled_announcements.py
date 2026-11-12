from django.core.management.base import BaseCommand

from announcements.views import publish_due_announcements


class Command(BaseCommand):
    help = "Publish announcements whose scheduled release time has arrived."

    def handle(self, *args, **options):
        published_count = publish_due_announcements()
        self.stdout.write(
            self.style.SUCCESS(
                f"Published {published_count} scheduled announcement(s)."
            )
        )
