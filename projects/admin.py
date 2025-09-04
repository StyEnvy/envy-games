from django.contrib import admin
from .models import Project

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "type", "status", "owner", "created_at", "updated_at", "archived_at")
    list_filter = ("type", "status", "owner")
    search_fields = ("name", "slug", "description")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at", "archived_at")
    raw_id_fields = ("owner",)
    list_select_related = ("owner",)
    prepopulated_fields = {"slug": ("name",)}  # helpful, slug still de-duped in model

    actions = ("mark_active", "mark_paused", "mark_archived", "mark_unarchived")

    def mark_active(self, request, queryset):
        for obj in queryset:
            obj.activate()
    mark_active.short_description = "Set status to Active"

    def mark_paused(self, request, queryset):
        for obj in queryset:
            obj.pause()
    mark_paused.short_description = "Set status to Paused"

    def mark_archived(self, request, queryset):
        for obj in queryset:
            obj.archive()
    mark_archived.short_description = "Set status to Archived"

    def mark_unarchived(self, request, queryset):
        for obj in queryset:
            obj.unarchive()
    mark_unarchived.short_description = "Unarchive (set Active)"
