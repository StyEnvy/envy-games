from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserRole(models.TextChoices):
    PROJECT_MANAGER = "pm", "Project Manager"
    DEVELOPER = "dev", "Developer"

class Profile(models.Model):
    """
    One-to-one user profile that stores an admin-assigned role.
    Registration & resets are admin-only in this project; role is set by staff.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=8, choices=UserRole.choices, default=UserRole.DEVELOPER, db_index=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def is_project_manager(self) -> bool:
        return self.role == UserRole.PROJECT_MANAGER

    @property
    def is_developer(self) -> bool:
        return self.role == UserRole.DEVELOPER

@receiver(post_save, sender=User)
def ensure_profile_exists(sender, instance: User, created: bool, **kwargs):
    if created:
        Profile.objects.create(user=instance)
