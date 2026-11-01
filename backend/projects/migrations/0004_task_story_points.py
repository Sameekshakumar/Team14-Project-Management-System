from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projects", "0003_taskdependency")]
    operations = [migrations.AddField(
        model_name="task", name="story_points",
        field=models.PositiveIntegerField(blank=True, null=True),
    )]
