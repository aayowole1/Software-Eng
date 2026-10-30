from django.db import migrations, models


def _move_legacy_notes(apps, schema_editor):
    meeting_draft = apps.get_model("meetings", "MeetingDraft")
    for draft in meeting_draft.objects.all():
        if draft.notes and not draft.transcript:
            draft.transcript = draft.notes
            draft.notes = ""
            draft.save(update_fields=["transcript", "notes"])


class Migration(migrations.Migration):

    dependencies = [
        ("meetings", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="meetingdraft",
            name="transcript",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(
            _move_legacy_notes,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="meetingdraft",
            name="notes",
            field=models.TextField(blank=True),
        ),
    ]
