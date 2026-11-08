"""Read-only by default; restricted to an explicitly recorded signup attempt."""

from bson import ObjectId
from bson.errors import InvalidId
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from accounts.provisioning import SignupRecoveryRefused, inspect_signup, repair_signup
from accounts.signup_attempts import SignupAttempt


class Command(BaseCommand):
    help = "Inspect an incomplete signup; --apply --workers-stopped restores its original pending application."

    def add_arguments(self, parser):
        parser.add_argument("attempt", help="Opaque SignupAttempt ID from the recovery alert; never an email.")
        parser.add_argument("--apply", action="store_true", help="Apply the bounded repair instead of a dry run.")
        parser.add_argument("--workers-stopped", action="store_true", help="Confirm signup workers are stopped during repair.")

    def handle(self, *args, **options):
        if options["apply"] and not options["workers_stopped"]:
            raise CommandError("Stop registration workers first, then use --apply --workers-stopped. The default dry run makes no changes.")
        try:
            attempt_id = ObjectId(options["attempt"])
        except (InvalidId, TypeError):
            raise CommandError("Use a valid opaque SignupAttempt ID.") from None
        try:
            attempt = SignupAttempt.objects.get(pk=attempt_id)
            result = repair_signup(attempt) if options["apply"] else inspect_signup(attempt)
        except SignupAttempt.DoesNotExist:
            raise CommandError("No recorded signup attempt exists for that ID. Unmarked accounts require separate investigation.") from None
        except SignupRecoveryRefused as error:
            raise CommandError(str(error)) from None
        except DatabaseError:
            raise CommandError("The database could not confirm completion. The attempt remains inspectable; retry after database recovery.") from None
        self.stdout.write("APPLY" if options["apply"] else "DRY RUN — no changes made")
        self.stdout.write(f"Signup attempt {attempt.pk}: {result['state']}.")
        for action in result["actions"]:
            self.stdout.write(f"- {action}")
