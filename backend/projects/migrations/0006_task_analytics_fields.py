from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projects", "0005_task_sprint")]

    operations = [
        migrations.AddField(
            model_name="task",
            name="priority",
            field=models.CharField(
                choices=[("Low", "Low"), ("Medium", "Medium"), ("High", "High"), ("Critical", "Critical")],
                default="Medium",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="due_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="task",
            name="completed_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
