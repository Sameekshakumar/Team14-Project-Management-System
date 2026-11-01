import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [("projects", "0004_task_story_points"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name="Sprint",
        fields=[
            ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ("name", models.CharField(max_length=100)),
            ("start_date", models.DateField()), ("end_date", models.DateField()),
            ("status", models.CharField(max_length=10, choices=[("Planned", "Planned"), ("Active", "Active")], default="Planned")),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("created_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, on_delete=django.db.models.deletion.SET_NULL)),
            ("project", models.ForeignKey(to="projects.project", related_name="sprints", on_delete=django.db.models.deletion.CASCADE)),
        ],
        options={"ordering": ["start_date", "created_at"], "constraints": [models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="sprint_valid_date_range")]},
    )]
