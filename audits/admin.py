from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
import json

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only admin for viewing audit logs with advanced filtering"""
    list_display = [
        'timestamp', 'action_badge', 'user_link',
        'object_link', 'project_link', 'ip_address'
    ]
    list_filter = ['action', ('timestamp', admin.DateFieldListFilter), 'content_type']
    search_fields = ['user__username', 'object_repr', 'ip_address', 'project__title']
    ordering = ['-timestamp']
    list_select_related = ['user', 'project', 'content_type']
    list_per_page = 50

    # Make everything read-only
    readonly_fields = [
        'timestamp', 'user', 'action', 'content_type', 'object_id',
        'object_repr', 'project', 'formatted_changes', 'ip_address', 'user_agent'
    ]

    fieldsets = (
        ('Action Details', {
            'fields': ('timestamp', 'user', 'action', 'project')
        }),
        ('Object Information', {
            'fields': ('content_type', 'object_id', 'object_repr')
        }),
        ('Changes', {
            'fields': ('formatted_changes',),
            'classes': ('wide',)
        }),
        ('Request Information', {
            'fields': ('ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def action_badge(self, obj):
        """Display action with color-coded badge"""
        colors = {
            'create': '#28a745',        # green
            'update': '#17a2b8',        # info blue
            'delete': '#dc3545',        # red
            'status': '#ffc107',        # yellow
            'member_add': '#20c997',    # teal
            'member_remove': '#e83e8c', # pink
            'task_move': '#6f42c1',     # purple
            'convert': '#fd7e14',       # orange
        }
        color = colors.get(obj.action, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            color, obj.get_action_display()
        )
    action_badge.short_description = 'Action'
    action_badge.admin_order_field = 'action'

    def user_link(self, obj):
        """Link to user in admin"""
        if obj.user:
            url = reverse('admin:auth_user_change', args=[obj.user.pk])
            return format_html('<a href="{}">{}</a>', url, obj.user.username)
        return '-'
    user_link.short_description = 'User'
    user_link.admin_order_field = 'user__username'

    def project_link(self, obj):
        """Link to project in admin"""
        if obj.project:
            url = reverse('admin:projects_project_change', args=[obj.project.pk])
            return format_html('<a href="{}">{}</a>', url, obj.project.title)
        return '-'
    project_link.short_description = 'Project'
    project_link.admin_order_field = 'project__title'

    def object_link(self, obj):
        """Try to link to the object if it still exists"""
        if obj.content_type and obj.object_id:
            try:
                model_class = obj.content_type.model_class()
                if model_class.objects.filter(pk=obj.object_id).exists():
                    url = reverse(
                        f'admin:{obj.content_type.app_label}_{obj.content_type.model}_change',
                        args=[obj.object_id]
                    )
                    return format_html('<a href="{}">{}</a>', url, obj.object_repr)
            except Exception:
                pass
        return obj.object_repr
    object_link.short_description = 'Object'

    def formatted_changes(self, obj):
        """Format the JSON changes field for display"""
        if not obj.changes:
            return '-'

        try:
            html_parts = ['<table style="width: 100%; border-collapse: collapse;">']
            html_parts.append('<tr><th style="text-align: left; padding: 5px; border-bottom: 1px solid #ddd;">Field</th>')
            html_parts.append('<th style="text-align: left; padding: 5px; border-bottom: 1px solid #ddd;">Old Value</th>')
            html_parts.append('<th style="text-align: left; padding: 5px; border-bottom: 1px solid #ddd;">New Value</th></tr>')

            for field, values in obj.changes.items():
                if isinstance(values, dict) and 'old' in values and 'new' in values:
                    html_parts.append('<tr>')
                    html_parts.append(f'<td style="padding: 5px; border-bottom: 1px solid #eee;"><strong>{field}</strong></td>')
                    html_parts.append(f'<td style="padding: 5px; border-bottom: 1px solid #eee; color: #dc3545;">{values["old"]}</td>')
                    html_parts.append(f'<td style="padding: 5px; border-bottom: 1px solid #eee; color: #28a745;">{values["new"]}</td>')
                    html_parts.append('</tr>')
                else:
                    html_parts.append('<tr>')
                    html_parts.append(f'<td style="padding: 5px; border-bottom: 1px solid #eee;"><strong>{field}</strong></td>')
                    html_parts.append(f'<td colspan="2" style="padding: 5px; border-bottom: 1px solid #eee;">{values}</td>')
                    html_parts.append('</tr>')

            html_parts.append('</table>')
            return mark_safe(''.join(html_parts))
        except Exception:
            return format_html(
                '<pre style="white-space: pre-wrap;">{}</pre>',
                json.dumps(obj.changes, indent=2)
            )
    formatted_changes.short_description = 'Changes'

    actions = ['export_as_csv']

    def export_as_csv(self, request, queryset):
        """Export selected audit logs as CSV"""
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="audit_logs.csv"'

        writer = csv.writer(response)
        writer.writerow(['Timestamp', 'User', 'Action', 'Object', 'Project', 'IP Address', 'Changes'])

        for log in queryset:
            writer.writerow([
                log.timestamp,
                log.user.username if log.user else '-',
                log.get_action_display(),
                log.object_repr,
                log.project.title if log.project else '-',
                log.ip_address or '-',
                json.dumps(log.changes) if log.changes else '-'
            ])

        return response
    export_as_csv.short_description = 'Export selected logs as CSV'
