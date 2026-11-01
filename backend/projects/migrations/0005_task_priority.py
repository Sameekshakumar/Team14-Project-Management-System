from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projects", "0004_task_due_date")]

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
    ]
