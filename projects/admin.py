from django.contrib import admin
from .models import Project, Board, Column, Task, Attachment


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['title', 'status', 'version', 'created_by', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['title', 'description']
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    fieldsets = (
        (None, {
            'fields': ('title', 'slug', 'version', 'status')
        }),
        ('Details', {
            'fields': ('description', 'created_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'board_type', 'is_active']
    list_filter = ['board_type', 'is_active']
    search_fields = ['name', 'project__title']
    list_select_related = ['project']


@admin.register(Column)
class ColumnAdmin(admin.ModelAdmin):
    list_display = ['name', 'board', 'position']
    list_filter = ['board__board_type']
    search_fields = ['name', 'board__name']
    ordering = ['board', 'position']
    list_select_related = ['board']


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'project', 'task_type', 'priority', 'assignee', 'column', 'is_roadmap_item', 'created_at']
    list_filter = ['task_type', 'priority', 'is_roadmap_item', 'created_at']
    search_fields = ['title', 'description']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    list_select_related = ['project', 'assignee', 'column', 'created_by']
    
    fieldsets = (
        (None, {
            'fields': ('title', 'project', 'column', 'position')
        }),
        ('Details', {
            'fields': ('description', 'task_type', 'priority', 'is_roadmap_item')
        }),
        ('Assignment', {
            'fields': ('assignee', 'created_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ['filename', 'task', 'uploaded_by', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['task__title', 'file']
    date_hierarchy = 'uploaded_at'
    ordering = ['-uploaded_at']
    list_select_related = ['task', 'uploaded_by']
    readonly_fields = ['uploaded_at']