import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("projects", "0003_taskdependency"),
    ]
    operations = [
        migrations.CreateModel(
            name="TaskComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField(max_length=5000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("author", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="task_comments", to=settings.AUTH_USER_MODEL)),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comments", to="projects.task")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.CreateModel(
            name="Mention",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("comment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mentions", to="collaboration.taskcomment")),
                ("mentioned_user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comment_mentions", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="mention",
            constraint=models.UniqueConstraint(fields=("comment", "mentioned_user"), name="unique_comment_mention"),
        ),
    ]
