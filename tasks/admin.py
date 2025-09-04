from django.contrib import admin, messages
from django.db import transaction
from django.urls import path
from django.shortcuts import redirect
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import Board, Column, Label, Task, Card, Subtask, Comment, Attachment, make_default_board


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "name", "kind", "is_default", "order", "make_default_link")
    list_filter = ("project", "kind", "is_default")
    search_fields = ("name",)
    ordering = ("project", "kind", "order", "name")
    actions = ("action_make_default",)
    list_select_related = ("project",)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/make-default/",
                self.admin_site.admin_view(self.make_default_view),
                name="boards_board_make_default",
            )
        ]
        return custom + urls

    def make_default_link(self, obj):
        return format_html(
            '<a class="button" href="{}">Make default</a>',
            self._make_default_url(obj.pk),
        )
    make_default_link.short_description = "Actions"

    def _make_default_url(self, pk: int) -> str:
        return f"./{pk}/make-default/"

    def make_default_view(self, request, pk: int):
        try:
            with transaction.atomic():
                board = make_default_board(pk)
            self.message_user(
                request,
                f"‘{board.name}’ is now the default {board.kind!r} board for project ‘{board.project}’.",
                level=messages.SUCCESS,
            )
        except Board.DoesNotExist:
            self.message_user(request, "Board not found.", level=messages.ERROR)
        except Exception as e:
            self.message_user(request, f"Failed to set default: {e}", level=messages.ERROR)
        return redirect(request.META.get("HTTP_REFERER", "/admin/"))

    def action_make_default(self, request, queryset):
        """Admin action: make each selected board default in its (project, kind) group."""
        success = 0
        errors = 0
        for b in queryset.select_related("project"):
            try:
                with transaction.atomic():
                    make_default_board(b.pk)
                success += 1
            except Exception:
                errors += 1
        if success:
            self.message_user(request, f"Made {success} board(s) default.", level=messages.SUCCESS)
        if errors:
            self.message_user(request, f"{errors} board(s) failed; check logs.", level=messages.ERROR)
    action_make_default.short_description = "Make selected board(s) default"


@admin.register(Column)
class ColumnAdmin(admin.ModelAdmin):
    list_display = ("id", "board", "name", "wip_limit", "order")
    list_filter = ("board__project", "board")
    search_fields = ("name",)
    autocomplete_fields = ("board",)
    ordering = ("board", "order", "name")
    list_select_related = ("board", "board__project")


class CardInline(admin.TabularInline):
    model = Card
    extra = 0
    fields = ("board", "column", "version_label", "order")
    autocomplete_fields = ("board", "column")
    verbose_name = "Placement"
    verbose_name_plural = "Placements"

    def get_formset(self, request, obj=None, **kwargs):
        # NOTE: we keep it simple; model.clean() enforces column↔board coherence.
        # Admin autocomplete keeps UX decent; per-row dynamic filtering would require custom JS.
        return super().get_formset(request, obj, **kwargs)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "kind",
        "status",
        "priority",
        "assignee",
        "score",
        "project",
        "created_at",
        "placements_summary",
    )
    list_filter = (
        "kind",
        "status",
        "priority",
        "labels",
        "project",
        "cards__board__kind",
        "cards__board",
        "cards__column",
    )
    search_fields = ("title", "description")
    autocomplete_fields = ("project", "assignee", "parent", "labels")
    filter_horizontal = ("labels",)
    inlines = [CardInline]
    ordering = ("-created_at",)
    readonly_fields = ("score", "created_at", "updated_at")
    list_select_related = ("project", "assignee")
    # M2M prefetch for labels inside admin list pages
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("project", "assignee").prefetch_related("labels", "cards__board", "cards__column")

    def placements_summary(self, obj):
        # CardManager already loads joins; we still ensure minimal queries
        qs = obj.cards.all()
        items = [f"{c.board.name}/{c.column.name}" for c in qs]
        return ", ".join(items) if items else "—"
    placements_summary.short_description = "Placements"


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ("id", "item", "project", "board", "column", "version_label", "order")
    list_filter = ("project", "board", "column")
    search_fields = ("item__title",)
    autocomplete_fields = ("item", "project", "board", "column")
    ordering = ("board", "column", "order")
    list_select_related = ("item", "project", "board", "column")

    def get_queryset(self, request):
        # CardManager defaults to with_joins(); we can still be explicit.
        return super().get_queryset(request).select_related("item", "project", "board", "column")


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "name", "color", "color_swatch")
    list_filter = ("project",)
    search_fields = ("name",)
    autocomplete_fields = ("project",)
    ordering = ("project", "name")
    list_select_related = ("project",)

    def color_swatch(self, obj):
        if not obj.color:
            return "—"
        # Show a small swatch; alpha (if present) won’t render in all browsers but still useful
        box = f'<span style="display:inline-block;width:1.25rem;height:1.25rem;border-radius:4px;vertical-align:middle;background:{obj.color};border:1px solid #444;"></span>'
        return mark_safe(box)
    color_swatch.short_description = " "

    # If you prefer an HTML color input (note: native input does not support alpha channel):
    # from django import forms
    # class LabelForm(forms.ModelForm):
    #     class Meta:
    #         model = Label
    #         fields = "__all__"
    #         widgets = {"color": forms.TextInput(attrs={"type": "color"})}
    # form = LabelForm


@admin.register(Subtask)
class SubtaskAdmin(admin.ModelAdmin):
    list_display = ("id", "task", "title", "is_done", "order")
    list_filter = ("is_done",)
    search_fields = ("title",)
    autocomplete_fields = ("task",)
    ordering = ("task", "order")
    list_select_related = ("task",)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "task", "created_by", "created_at")
    list_filter = ("created_by",)
    search_fields = ("body",)
    autocomplete_fields = ("task", "created_by")
    ordering = ("-created_at",)
    list_select_related = ("task", "created_by")


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "task", "mime_type", "pretty_size", "uploaded_by", "uploaded_at")
    list_filter = ("mime_type", "uploaded_by")
    search_fields = ("file",)
    autocomplete_fields = ("task", "uploaded_by")
    ordering = ("-uploaded_at",)
    list_select_related = ("task", "uploaded_by")

    def pretty_size(self, obj):
        # simple human-readable size
        size = int(obj.size_bytes or 0)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size} {unit}"
            size //= 1024
        return f"{size} PB"
    pretty_size.short_description = "Size"
