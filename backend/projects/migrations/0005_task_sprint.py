from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("projects", "0004_task_story_points"), ("sprints", "0001_initial")]
    operations = [migrations.AddField(
        model_name="task", name="sprint",
        field=models.ForeignKey(to="sprints.sprint", on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name="items"),
    )]
