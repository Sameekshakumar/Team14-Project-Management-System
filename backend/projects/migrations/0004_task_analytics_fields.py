from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projects", "0003_taskdependency")]
    operations = [
        migrations.AddField("task", "priority", models.CharField(
            choices=[("Low", "Low"), ("Medium", "Medium"), ("High", "High"), ("Critical", "Critical")],
            default="Medium", max_length=10,
        )),
        migrations.AddField("task", "due_date", models.DateField(blank=True, db_index=True, null=True)),
        migrations.AddField("task", "completed_at", models.DateTimeField(blank=True, db_index=True, null=True)),
    ]
