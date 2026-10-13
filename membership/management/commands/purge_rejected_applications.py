from django.core.management.base import BaseCommand

from membership.models import REJECTED_RETENTION, purge_old_rejected_applications


class Command(BaseCommand):
    help = f"Delete rejected membership applications older than {REJECTED_RETENTION.days} days."

    def handle(self, *args, **options):
        deleted = purge_old_rejected_applications()
        self.stdout.write(f"Deleted {deleted} rejected application(s) older than {REJECTED_RETENTION.days} days.")
