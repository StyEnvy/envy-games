from __future__ import annotations

import csv
from typing import Any

from django import forms
from django.contrib import admin
from django.db import models
from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse

from .models import TrackedProject, TrackedTask, TimeEntry


# ----------------------------
# List filters
# ----------------------------

class ActiveFilter(admin.SimpleListFilter):
    title = "Active"
    parameter_name = "active"

    def lookups(self, request: HttpRequest, model_admin: admin.ModelAdmin):
        return (("yes", "Active"), ("no", "Inactive"))

    def queryset(self, request: HttpRequest, queryset: models.QuerySet):
        val = self.value()
        if val == "yes":
            return queryset.filter(is_active=True)
        if val == "no":
            return queryset.filter(is_active=False)
        return queryset


class BillableFilter(admin.SimpleListFilter):
    title = "Billable"
    parameter_name = "billable"

    def lookups(self, request: HttpRequest, model_admin: admin.ModelAdmin):
        return (("yes", "Billable"), ("no", "Non-billable"))

    def queryset(self, request: HttpRequest, queryset: models.QuerySet):
        val = self.value()
        if val == "yes":
            return queryset.filter(billable=True)
        if val == "no":
            return queryset.filter(billable=False)
        return queryset


# ----------------------------
# Inlines
# ----------------------------

class TrackedTaskInline(admin.TabularInline):
    model = TrackedTask
    extra = 0
    show_change_link = True
    fields = ("title", "slug", "is_active", "external_ref", "source_task_id", "created_at", "updated_at")
    readonly_fields = ("slug", "created_at", "updated_at")


# ----------------------------
# Project Admin
# ----------------------------

@admin.register(TrackedProject)
class TrackedProjectAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "is_active",
        "external_ref",
        "source_project_id",
        "task_count",
        "entry_count",
        "created_at",
        "updated_at",
    )
    list_filter = (ActiveFilter,)
    search_fields = ("title", "slug", "external_ref")
    readonly_fields = ("uid", "slug", "created_at", "updated_at")
    inlines = [TrackedTaskInline]
    list_per_page = 50

    def get_queryset(self, request: HttpRequest):
        qs = super().get_queryset(request)
        return qs.annotate(_task_count=Count("tasks"), _entry_count=Count("entries"))

    @admin.display(ordering="_task_count", description="Tasks")
    def task_count(self, obj: TrackedProject) -> int:
        return getattr(obj, "_task_count", 0)

    @admin.display(ordering="_entry_count", description="Entries")
    def entry_count(self, obj: TrackedProject) -> int:
        return getattr(obj, "_entry_count", 0)

    # Bulk actions
    @admin.action(description="Mark selected projects as ACTIVE")
    def mark_active(self, request: HttpRequest, queryset: models.QuerySet):
        queryset.update(is_active=True)

    @admin.action(description="Mark selected projects as INACTIVE")
    def mark_inactive(self, request: HttpRequest, queryset: models.QuerySet):
        queryset.update(is_active=False)

    actions = ("mark_active", "mark_inactive")


# ----------------------------
# Task Admin
# ----------------------------

@admin.register(TrackedTask)
class TrackedTaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "project",
        "is_active",
        "external_ref",
        "source_task_id",
        "entry_count",
        "created_at",
        "updated_at",
    )
    list_filter = (ActiveFilter, "project")
    search_fields = ("title", "slug", "external_ref", "project__title")
    readonly_fields = ("uid", "slug", "created_at", "updated_at")
    autocomplete_fields = ("project",)
    list_select_related = ("project",)
    list_per_page = 50

    def get_queryset(self, request: HttpRequest):
        qs = super().get_queryset(request)
        return qs.select_related("project").annotate(_entry_count=Count("entries"))

    @admin.display(ordering="_entry_count", description="Entries")
    def entry_count(self, obj: TrackedTask) -> int:
        return getattr(obj, "_entry_count", 0)

    # Bulk actions
    @admin.action(description="Mark selected tasks as ACTIVE")
    def mark_active(self, request: HttpRequest, queryset: models.QuerySet):
        queryset.update(is_active=True)

    @admin.action(description="Mark selected tasks as INACTIVE")
    def mark_inactive(self, request: HttpRequest, queryset: models.QuerySet):
        queryset.update(is_active=False)

    actions = ("mark_active", "mark_inactive")


# ----------------------------
# TimeEntry Admin
# ----------------------------

class TimeEntryAdminForm(forms.ModelForm):
    """
    Keep the admin ergonomic: when a task is chosen, ensure the project matches it.
    Model.save() already enforces this, but doing it in the form keeps the admin UI consistent.
    """
    class Meta:
        model = TimeEntry
        fields = ("project", "task", "user", "work_date", "duration_minutes", "billable", "notes")

    def clean(self):
        cleaned = super().clean()
        task = cleaned.get("task")
        if task is not None:
            cleaned["project"] = task.project
        return cleaned


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    form = TimeEntryAdminForm

    date_hierarchy = "work_date"
    list_display = (
        "work_date",
        "user",
        "project",
        "task",
        "duration_hm",
        "billable",
        "notes_short",
        "created_at",
    )
    list_filter = (BillableFilter, "project", "task", "user")
    search_fields = (
        "notes",
        "project__title",
        "task__title",
        "user__username",
        "user__first_name",
        "user__last_name",
    )
    autocomplete_fields = ("project", "task", "user")
    readonly_fields = ("uid", "created_at", "updated_at")
    fields = ("project", "task", "user", "work_date", "duration_minutes", "billable", "notes", "uid", "created_at", "updated_at")
    list_select_related = ("project", "task", "user")
    list_per_page = 50

    def get_queryset(self, request: HttpRequest):
        return super().get_queryset(request).select_related("project", "task", "user")

    # --------- nice display helpers ---------

    @admin.display(description="Duration")
    def duration_hm(self, obj: TimeEntry) -> str:
        m = obj.duration_minutes
        h, r = divmod(m, 60)
        if h and r:
            return f"{h}h {r}m"
        if h:
            return f"{h}h"
        return f"{r}m"

    @admin.display(description="Notes")
    def notes_short(self, obj: TimeEntry) -> str:
        if not obj.notes:
            return ""
        s = obj.notes.strip().replace("\n", " ")
        return s if len(s) <= 80 else f"{s[:77]}..."

    # --------- actions ---------

    @admin.action(description="Mark selected entries as BILLABLE")
    def mark_billable(self, request: HttpRequest, queryset: models.QuerySet):
        queryset.update(billable=True)

    @admin.action(description="Mark selected entries as NON-billable")
    def mark_non_billable(self, request: HttpRequest, queryset: models.QuerySet):
        queryset.update(billable=False)

    @admin.action(description="Export selected entries to CSV")
    def export_csv(self, request: HttpRequest, queryset: models.QuerySet) -> HttpResponse:
        qs = queryset.select_related("project", "task", "user")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="time_entries.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "id",
                "uid",
                "work_date",
                "user",
                "project",
                "task",
                "duration_minutes",
                "billable",
                "notes",
                "created_at",
                "updated_at",
            ]
        )
        for e in qs:
            writer.writerow(
                [
                    e.pk,
                    str(e.uid),
                    e.work_date.isoformat(),
                    str(e.user),
                    e.project.title,
                    e.task.title,
                    e.duration_minutes,
                    "yes" if e.billable else "no",
                    (e.notes or "").replace("\r", " ").replace("\n", " "),
                    e.created_at.isoformat(timespec="seconds"),
                    e.updated_at.isoformat(timespec="seconds"),
                ]
            )
        return response

    actions = ("mark_billable", "mark_non_billable", "export_csv")
