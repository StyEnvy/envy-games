from django.contrib import admin
from .models import Asset, AssetVersion, AssetProject


class AssetVersionInline(admin.TabularInline):
    model = AssetVersion
    extra = 0
    fields = ("number", "original_filename", "content_type", "size_bytes", "sha256", "created_at", "uploaded_by")
    readonly_fields = ("created_at",)
    ordering = ("-number",)


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("title", "asset_type", "created_by", "created_at", "current_version_display")
    search_fields = ("title", "description", "tags", "slug")
    list_filter = ("asset_type", "created_at")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [AssetVersionInline]

    def current_version_display(self, obj):
        return f"v{obj.current_version.number}" if obj.current_version else "-"
    current_version_display.short_description = "Current Version"


@admin.register(AssetProject)
class AssetProjectAdmin(admin.ModelAdmin):
    list_display = ("asset", "project", "added_by", "added_at")
    search_fields = ("asset__title", "project__title")
    list_filter = ("added_at",)
