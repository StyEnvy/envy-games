from django.db.models.signals import post_save, pre_save, post_delete, pre_delete
from django.dispatch import receiver
from django.contrib.auth.models import User

from projects.models import Project, ProjectMembership, Task, Board, Column
from accounts.models import Profile, UserRole
from .models import AuditLog, AuditAction

# ---------------------------
# Helpers
# ---------------------------

def _field_changes(old_obj, new_obj, fields, display_map=None):
    """
    Diff simple fields on two instances.
    display_map: optional {field: (old_display, new_display)} function pairs or lambdas
    """
    changes = {}
    for f in fields:
        old_v = getattr(old_obj, f)
        new_v = getattr(new_obj, f)
        if old_v != new_v:
            # Pretty values if requested
            if display_map and f in display_map:
                ofn, nfn = display_map[f]
                changes[f] = {"old": str(ofn(old_v)), "new": str(nfn(new_v))}
            else:
                changes[f] = {"old": str(old_v), "new": str(new_v)}
    return changes


# =========================================================
# PROJECT
# =========================================================

@receiver(pre_save, sender=Project)
def audit_project_changes(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Project.objects.get(pk=instance.pk)
            fields = ["title", "status", "version", "description", "project_type"]
            changes = _field_changes(old, instance, fields)
            if changes:
                instance._audit_changes = changes
        except Project.DoesNotExist:
            pass


@receiver(post_save, sender=Project)
def log_project_save(sender, instance, created, **kwargs):
    if created:
        AuditLog.log(obj=instance, action=AuditAction.CREATE, project=instance)
    elif hasattr(instance, "_audit_changes"):
        action = AuditAction.STATUS_CHANGE if "status" in instance._audit_changes else AuditAction.UPDATE
        AuditLog.log(obj=instance, action=action, changes=instance._audit_changes, project=instance)
        delattr(instance, "_audit_changes")


@receiver(pre_delete, sender=Project)
def log_project_delete(sender, instance, **kwargs):
    # Log before deletion so FK(project) is valid; will be set NULL after delete due to SET_NULL.
    AuditLog.log(obj=instance, action=AuditAction.DELETE, project=instance)


# =========================================================
# PROJECT MEMBERSHIP
# =========================================================

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
        AuditLog.log(
            obj=instance,
            action=AuditAction.MEMBER_ADD,
            changes={"user": instance.user.username, "is_active": instance.is_active},
            project=instance.project,
        )
    elif hasattr(instance, "_audit_membership_changes"):
        AuditLog.log(
            obj=instance,
            action=AuditAction.UPDATE,
            changes=instance._audit_membership_changes,
            project=instance.project,
        )
        delattr(instance, "_audit_membership_changes")


@receiver(post_delete, sender=ProjectMembership)
def log_membership_removal(sender, instance, **kwargs):
    # Always log removal; user will be inferred from middleware if available.
    AuditLog.log(
        obj=instance,
        action=AuditAction.MEMBER_REMOVE,
        changes={"user": getattr(instance.user, "username", None)},
        project=instance.project,
    )


# =========================================================
# TASK
# =========================================================

@receiver(pre_save, sender=Task)
def audit_task_changes(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Task.objects.select_related("column__board").get(pk=instance.pk)
            display_map = {
                "assignee_id": (
                    lambda v: getattr(old.assignee, "username", None),
                    lambda v: getattr(instance.assignee, "username", None),
                )
            }
            base_changes = _field_changes(
                old,
                instance,
                fields=["title", "description", "task_type", "priority", "assignee_id", "is_roadmap_item"],
                display_map=display_map,
            )

            # Movement between columns/positions
            move_changes = {}
            if old.column_id != instance.column_id:
                move_changes["column"] = {
                    "old": f"{getattr(old.column, 'name', None)}",
                    "new": f"{getattr(instance.column, 'name', None)}",
                }
                # Also show board change if any
                old_board = getattr(getattr(old, "column", None), "board", None)
                new_board = getattr(getattr(instance, "column", None), "board", None)
                if old_board != new_board:
                    move_changes["board"] = {
                        "old": f"{getattr(old_board, 'name', None)}",
                        "new": f"{getattr(new_board, 'name', None)}",
                    }
            if old.position != instance.position:
                move_changes["position"] = {"old": str(old.position), "new": str(instance.position)}

            # Tag action type preference for post_save
            action = None
            changes = {**base_changes, **move_changes}
            if "is_roadmap_item" in base_changes:
                # Conversions between roadmap and tasks
                old_flag = base_changes["is_roadmap_item"]["old"].lower() == "true"
                new_flag = base_changes["is_roadmap_item"]["new"].lower() == "true"
                if old_flag and not new_flag:
                    action = AuditAction.CONVERT
            elif move_changes:
                action = AuditAction.TASK_MOVE
            elif base_changes:
                action = AuditAction.UPDATE

            if action:
                instance._audit_task_action = action
                instance._audit_task_changes = changes

        except Task.DoesNotExist:
            pass


@receiver(post_save, sender=Task)
def log_task_save(sender, instance, created, **kwargs):
    if created:
        AuditLog.log(obj=instance, action=AuditAction.CREATE)
    elif hasattr(instance, "_audit_task_action"):
        AuditLog.log(
            obj=instance,
            action=instance._audit_task_action,
            changes=getattr(instance, "_audit_task_changes", {}),
        )
        if hasattr(instance, "_audit_task_changes"):
            delattr(instance, "_audit_task_changes")
        delattr(instance, "_audit_task_action")


@receiver(post_delete, sender=Task)
def log_task_delete(sender, instance, **kwargs):
    AuditLog.log(obj=instance, action=AuditAction.DELETE)


# =========================================================
# BOARD
# =========================================================

@receiver(pre_save, sender=Board)
def audit_board_changes(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Board.objects.get(pk=instance.pk)
            changes = _field_changes(old, instance, fields=["name", "board_type", "is_active"])
            if changes:
                instance._audit_board_changes = changes
        except Board.DoesNotExist:
            pass


@receiver(post_save, sender=Board)
def log_board_save(sender, instance, created, **kwargs):
    if created:
        AuditLog.log(obj=instance, action=AuditAction.CREATE)
    elif hasattr(instance, "_audit_board_changes"):
        AuditLog.log(obj=instance, action=AuditAction.UPDATE, changes=instance._audit_board_changes)
        delattr(instance, "_audit_board_changes")


@receiver(post_delete, sender=Board)
def log_board_delete(sender, instance, **kwargs):
    AuditLog.log(obj=instance, action=AuditAction.DELETE)


# =========================================================
# COLUMN
# =========================================================

@receiver(pre_save, sender=Column)
def audit_column_changes(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Column.objects.get(pk=instance.pk)
            changes = _field_changes(old, instance, fields=["name", "position"])
            if changes:
                instance._audit_column_changes = changes
        except Column.DoesNotExist:
            pass


@receiver(post_save, sender=Column)
def log_column_save(sender, instance, created, **kwargs):
    if created:
        AuditLog.log(obj=instance, action=AuditAction.CREATE)
    elif hasattr(instance, "_audit_column_changes"):
        AuditLog.log(obj=instance, action=AuditAction.UPDATE, changes=instance._audit_column_changes)
        delattr(instance, "_audit_column_changes")


@receiver(post_delete, sender=Column)
def log_column_delete(sender, instance, **kwargs):
    AuditLog.log(obj=instance, action=AuditAction.DELETE)


# =========================================================
# ACCOUNTS: USER & PROFILE
# =========================================================

@receiver(pre_save, sender=User)
def audit_user_changes(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = User.objects.get(pk=instance.pk)
            changes = _field_changes(
                old,
                instance,
                fields=["username", "first_name", "last_name", "email", "is_active", "is_staff", "is_superuser"],
            )
            if changes:
                instance._audit_user_changes = changes
        except User.DoesNotExist:
            pass


@receiver(post_save, sender=User)
def log_user_save(sender, instance, created, **kwargs):
    if created:
        AuditLog.log(obj=instance, action=AuditAction.CREATE)
    elif hasattr(instance, "_audit_user_changes"):
        AuditLog.log(obj=instance, action=AuditAction.UPDATE, changes=instance._audit_user_changes)
        delattr(instance, "_audit_user_changes")


@receiver(post_delete, sender=User)
def log_user_delete(sender, instance, **kwargs):
    AuditLog.log(obj=instance, action=AuditAction.DELETE)


@receiver(pre_save, sender=Profile)
def audit_profile_changes(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Profile.objects.select_related("user").get(pk=instance.pk)
            changes = _field_changes(old, instance, fields=["role"])
            if changes:
                # Pretty role display
                changes["role"]["old"] = dict(UserRole.choices).get(changes["role"]["old"], changes["role"]["old"])
                changes["role"]["new"] = dict(UserRole.choices).get(changes["role"]["new"], changes["role"]["new"])
                instance._audit_profile_changes = changes
        except Profile.DoesNotExist:
            pass


@receiver(post_save, sender=Profile)
def log_profile_save(sender, instance, created, **kwargs):
    if created:
        AuditLog.log(obj=instance, action=AuditAction.CREATE)
    elif hasattr(instance, "_audit_profile_changes"):
        AuditLog.log(obj=instance, action=AuditAction.UPDATE, changes=instance._audit_profile_changes)
        delattr(instance, "_audit_profile_changes")


@receiver(post_delete, sender=Profile)
def log_profile_delete(sender, instance, **kwargs):
    AuditLog.log(obj=instance, action=AuditAction.DELETE)
