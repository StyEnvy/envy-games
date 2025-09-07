from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count, Q

from .models import (
    Project, Task,
    ProjectMembership,
)


class ProjectMembershipInline(admin.TabularInline):
    """Inline admin for managing project members directly from project page"""
    model = ProjectMembership
    extra = 1
    fields = ['user', 'is_active', 'joined_at', 'added_by']
    readonly_fields = ['joined_at']
    autocomplete_fields = ['user', 'added_by']


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'project_type', 'status', 'version',
        'created_by', 'member_count', 'created_at'
    ]
    list_filter = ['status', 'project_type', ('created_at', admin.DateFieldListFilter)]
    search_fields = ['title', 'description']
    prepopulated_fields = {'slug': ('title',)}
    ordering = ['-created_at']
    inlines = [ProjectMembershipInline]

    fieldsets = (
        (None, {
            'fields': ('title', 'slug', 'project_type')
        }),
        ('Status & Version', {
            'fields': ('status', 'version')
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

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            active_member_count=Count(
                'memberships',
                filter=Q(memberships__is_active=True)
            )
        )

    def member_count(self, obj):
        """Display number of active members"""
        count = getattr(obj, 'active_member_count', None)
        if count is None:
            count = obj.memberships.filter(is_active=True).count()
        return format_html('<span class="badge">{}</span>', count)

    member_count.short_description = 'Members'
    member_count.admin_order_field = 'active_member_count'


@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'project', 'status_badge',
        'is_active', 'added_by', 'joined_at'
    ]
    list_filter = ['is_active', ('joined_at', admin.DateFieldListFilter)]
    search_fields = ['user__username', 'user__email', 'project__title']
    ordering = ['-joined_at']
    list_select_related = ['user', 'project', 'added_by']
    autocomplete_fields = ['user', 'project', 'added_by']

    fieldsets = (
        (None, {
            'fields': ('project', 'user')
        }),
        ('Status', {
            'fields': ('is_active', 'added_by')
        }),
        ('Timestamps', {
            'fields': ('joined_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ['joined_at', 'updated_at']

    def status_badge(self, obj):
        """Color-coded Active/Inactive badge"""
        color = '#28a745' if obj.is_active else '#6c757d'
        text = 'Active' if obj.is_active else 'Inactive'
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color, text
        )

    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'is_active'

    actions = ['activate_memberships', 'deactivate_memberships']

    def activate_memberships(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} membership(s) activated.')

    activate_memberships.short_description = 'Activate selected memberships'

    def deactivate_memberships(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} membership(s) deactivated.')

    deactivate_memberships.short_description = 'Deactivate selected memberships'


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'project', 'task_type', 'priority',
        'assignee', 'column', 'is_roadmap_item', 'created_at'
    ]
    list_filter = [
        'task_type', 'priority', 'is_roadmap_item',
        ('created_at', admin.DateFieldListFilter)
    ]
    search_fields = ['title', 'description']
    ordering = ['-created_at']
    list_select_related = ['project', 'assignee', 'column', 'created_by']
    autocomplete_fields = ['assignee', 'project']

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
