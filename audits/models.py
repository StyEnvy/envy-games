from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models

class AuditAction(models.TextChoices):
    CREATE = "create", "Created"
    UPDATE = "update", "Updated"
    DELETE = "delete", "Deleted"
    STATUS_CHANGE = "status", "Status Changed"
    MEMBER_ADD = "member_add", "Member Added"
    MEMBER_REMOVE = "member_remove", "Member Removed"
    TASK_MOVE = "task_move", "Task Moved"
    CONVERT = "convert", "Converted"

class AuditLog(models.Model):
    """
    Tracks changes to projects, tasks, and memberships.
    Provides audit trail for compliance and debugging.
    """
    # What was changed
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True)
    object_id = models.PositiveIntegerField(null=True)
    object_repr = models.CharField(max_length=200)  # String representation if object deleted

    # What action was taken
    action = models.CharField(max_length=20, choices=AuditAction.choices)

    # Who did it and when
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_logs"
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    # What changed (JSON field for flexibility)
    changes = models.JSONField(default=dict, blank=True)

    # Additional context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    # For linking related logs
    # Use string reference to avoid circular import with Project
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs"
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["user", "timestamp"]),
            models.Index(fields=["project", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} {self.object_repr} by {self.user} at {self.timestamp}"

    @classmethod
    def log(cls, obj, action, user=None, changes=None, request=None, project=None):
        """
        Create an audit log entry with smart defaults:
        - user/request are inferred from thread-local middleware if not supplied
        - project is inferred from common relations (project, board.project, column.board.project, membership.project)
        """
        from django.contrib.contenttypes.models import ContentType
        from django.apps import apps

        # Lazy imports to avoid circulars
        Project = apps.get_model("projects", "Project")
        ProjectMembership = apps.get_model("projects", "ProjectMembership")
        Task = apps.get_model("projects", "Task")
        Board = apps.get_model("projects", "Board")
        Column = apps.get_model("projects", "Column")

        # Fallback to thread-local user/request
        if user is None:
            try:
                from .middleware import get_current_user, get_current_request
                user = get_current_user()
                request = request or get_current_request()
            except Exception:
                pass

        # Infer project if not explicitly given
        if project is None:
            try:
                if hasattr(obj, "project"):
                    project = obj.project
                elif isinstance(obj, Task):
                    project = getattr(getattr(obj, "column", None), "board", None)
                    project = getattr(project, "project", None)
                elif isinstance(obj, Column):
                    project = getattr(getattr(obj, "board", None), "project", None)
                elif isinstance(obj, Board):
                    project = getattr(obj, "project", None)
                elif isinstance(obj, ProjectMembership):
                    project = obj.project
                elif isinstance(obj, Project):
                    project = obj
            except Exception:
                project = None

        content_type = ContentType.objects.get_for_model(obj.__class__)

        log_entry = cls.objects.create(
            content_type=content_type,
            object_id=getattr(obj, "pk", None),
            object_repr=str(obj)[:200],
            action=action,
            user=user,
            changes=changes or {},
            project=project,
        )

        # Attach request metadata if we have it
        if request:
            log_entry.ip_address = cls._get_client_ip(request)
            log_entry.user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
            log_entry.save(update_fields=["ip_address", "user_agent"])

        return log_entry

    @staticmethod
    def _get_client_ip(request):
        """Extract client IP from request"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip