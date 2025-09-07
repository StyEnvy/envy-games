from django.contrib import admin

from .models import TrackedProject, TrackedTask, TimeEntry


@admin.register(TrackedProject)
class TrackedProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "external_ref", "created_at", "updated_at")
    search_fields = ("title", "external_ref")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("title",)}


@admin.register(TrackedTask)
class TrackedTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "is_active", "external_ref", "created_at", "updated_at")
    search_fields = ("title", "project__title", "external_ref")
    list_filter = ("is_active", "project")
    autocomplete_fields = ("project",)
    prepopulated_fields = {"slug": ("title",)}


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ("work_date", "project", "task", "user", "duration_minutes", "billable")
    list_filter = ("project", "task", "user", "billable", "work_date")
    search_fields = ("notes", "project__title", "task__title", "user__username", "user__email")
    autocomplete_fields = ("project", "task", "user")
    date_hierarchy = "work_date"