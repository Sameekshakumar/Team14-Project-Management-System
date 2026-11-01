from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projects", "0003_taskdependency")]

    operations = [
        migrations.AddField(
            model_name="task",
            name="due_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
    ]
