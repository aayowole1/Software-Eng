from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tasks", "0002_description_limit")]

    operations = [
        migrations.AlterField(
            model_name="task",
            name="priority",
            field=models.CharField(
                choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent")],
                default="medium",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="task",
            name="status",
            field=models.CharField(
                choices=[("todo", "To do"), ("in_progress", "In progress"), ("under_review", "Under Review"), ("done", "Done")],
                default="todo",
                max_length=20,
            ),
        ),
    ]
