from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projects", "0005_task_priority")]

    operations = [
        migrations.AddField(
            model_name="task",
            name="completed_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
