from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("announcements", "0006_merge_resource_and_comments"),
    ]

    operations = [
        migrations.RenameField(
            model_name="announcement",
            old_name="audience",
            new_name="committee",
        ),
    ]
