import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("collaboration", "0001_initial")]

    operations = [
        migrations.RemoveField(model_name="taskcomment", name="mentioned_users"),
        migrations.AddField(
            model_name="taskcomment",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.CreateModel(
            name="Mention",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("comment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mentions", to="collaboration.taskcomment")),
                ("mentioned_user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comment_mentions", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name="taskcomment",
            name="mentioned_users",
            field=models.ManyToManyField(blank=True, related_name="mentioned_in_comments", through="collaboration.Mention", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddConstraint(
            model_name="mention",
            constraint=models.UniqueConstraint(fields=("comment", "mentioned_user"), name="unique_comment_mention"),
        ),
    ]
