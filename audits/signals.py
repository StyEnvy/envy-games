from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver

from projects.models import Project, ProjectMembership
from .models import AuditLog, AuditAction


@receiver(pre_save, sender=Project)
def audit_project_changes(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Project.objects.get(pk=instance.pk)
            changes = {}
            fields_to_track = ["title", "status", "version", "description", "project_type"]
            for field in fields_to_track:
                old_value = getattr(old, field)
                new_value = getattr(instance, field)
                if old_value != new_value:
                    changes[field] = {"old": str(old_value), "new": str(new_value)}
            if changes:
                instance._audit_changes = changes
                instance._audit_old_status = old.status
        except Project.DoesNotExist:
            pass


@receiver(post_save, sender=Project)
def log_project_save(sender, instance, created, **kwargs):
    user = getattr(instance, "_audit_user", None)
    if created:
        AuditLog.log(
            obj=instance,
            action=AuditAction.CREATE,
            user=user or instance.created_by,
            project=instance,
        )
    elif hasattr(instance, "_audit_changes"):
        action = AuditAction.STATUS_CHANGE if "status" in instance._audit_changes else AuditAction.UPDATE
        AuditLog.log(
            obj=instance,
            action=action,
            user=user,
            changes=instance._audit_changes,
            project=instance,
        )
        delattr(instance, "_audit_changes")


@receiver(pre_save, sender=ProjectMembership)
def audit_membership_changes(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = ProjectMembership.objects.get(pk=instance.pk)
            changes = {}
            if old.is_active != instance.is_active:
                changes["is_active"] = {"old": str(old.is_active), "new": str(instance.is_active)}
            if old.added_by_id != instance.added_by_id:
                old_added = getattr(old.added_by, "username", None)
                new_added = getattr(instance.added_by, "username", None)
                changes["added_by"] = {"old": str(old_added), "new": str(new_added)}
            if changes:
                changes["user"] = instance.user.username
                instance._audit_membership_changes = changes
        except ProjectMembership.DoesNotExist:
            pass


@receiver(post_save, sender=ProjectMembership)
def log_membership_change(sender, instance, created, **kwargs):
    if created:
        user = getattr(instance, "_audit_user", instance.added_by)
        AuditLog.log(
            obj=instance,
            action=AuditAction.MEMBER_ADD,
            user=user,
            changes={"user": instance.user.username, "is_active": instance.is_active},
            project=instance.project,
        )
    elif hasattr(instance, "_audit_membership_changes"):
        user = getattr(instance, "_audit_user", None)
        AuditLog.log(
            obj=instance,
            action=AuditAction.UPDATE,
            user=user,
            changes=instance._audit_membership_changes,
            project=instance.project,
        )
        delattr(instance, "_audit_membership_changes")


@receiver(post_delete, sender=ProjectMembership)
def log_membership_removal(sender, instance, **kwargs):
    user = getattr(instance, "_audit_user", None)
    if user:
        AuditLog.log(
            obj=instance,
            action=AuditAction.MEMBER_REMOVE,
            user=user,
            changes={"user": instance.user.username},
            project=instance.project,
        )
