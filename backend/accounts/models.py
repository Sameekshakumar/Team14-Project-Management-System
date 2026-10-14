from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
import uuid


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).strip().lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True, max_length=100)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email
class Workspace(models.Model):
    id = models.UUIDField(
    primary_key=True,
    default=uuid.uuid4,
    editable=False,
)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    owner = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="owned_workspaces",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name