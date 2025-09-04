from django.contrib import admin
from .models import Asset, AssetVersion

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("name","project","kind","created_by","created_at")
    list_filter = ("kind","project")
    search_fields = ("name","description")

@admin.register(AssetVersion)
class AssetVersionAdmin(admin.ModelAdmin):
    list_display = ("asset","is_primary","uploaded_by","uploaded_at","size_bytes")
    list_filter = ("is_primary",)
