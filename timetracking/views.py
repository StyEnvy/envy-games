from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional, Tuple
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseBadRequest
from django.db import models, transaction
from django.apps import apps as django_apps
from django.db.models import Case, When, IntegerField, Q, Count, Min, Max, Sum
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from django.views.decorators.http import require_GET
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.core.paginator import Paginator, EmptyPage

from .forms import TimeEntryForm
from .models import TimeEntry, TrackedProject, TrackedTask

RESULT_LIMIT = 50

class TimeEntryView(LoginRequiredMixin, View):
    template_name = "timetracking/home.html"
    max_recent: int = 30  # show more by default

    def _selected_project_id(self, request) -> Optional[int]:
        val = request.GET.get("project")
        try:
            return int(val) if val else None
        except (TypeError, ValueError):
            return None

    def get_context(self, request, form: TimeEntryForm, selected_project_id: Optional[int]) -> Dict[str, Any]:
        recent_entries = (
            TimeEntry.objects.filter(user=request.user)
            .select_related("project", "task")
            .order_by("-work_date", "-created_at")[: self.max_recent]
        )

        # ---- Role/user display bits ----
        profile = getattr(request.user, "profile", None)
        role_code = getattr(profile, "role", None)
        role_display = profile.get_role_display() if profile else "—"
        is_pm = bool(getattr(profile, "is_project_manager", False))
        is_dev = bool(getattr(profile, "is_developer", False))

        user_display_name = request.user.get_full_name() or request.user.get_username()

        return {
            "form": form,
            "recent_entries": recent_entries,
            "selected_project_id": selected_project_id,
            # expose to template
            "user_display_name": user_display_name,
            "user_role": role_code,
            "user_role_display": role_display,
            "is_pm": is_pm,
            "is_dev": is_dev,
            # convenience for the metrics button
            "can_view_metrics": is_pm,
        }

    def get(self, request, *args, **kwargs):
        selected_project_id = self._selected_project_id(request)
        initial = {}
        if selected_project_id:
            try:
                initial["project"] = TrackedProject.objects.only("id").get(id=selected_project_id)
            except TrackedProject.DoesNotExist:
                selected_project_id = None

        form = TimeEntryForm(initial=initial)
        return render(request, self.template_name, self.get_context(request, form, selected_project_id))

    def post(self, request, *args, **kwargs):
        form = TimeEntryForm(request.POST)
        selected_project_id = None

        if form.is_valid():
            obj: TimeEntry = form.save(commit=False)
            obj.user = request.user
            obj.save()
            messages.success(request, "Time recorded.")
            selected_project_id = obj.project_id
            url = f"{reverse('timetracking:home')}?project={selected_project_id}"
            return redirect(url)

        prj = form.data.get("project")
        try:
            selected_project_id = int(prj) if prj else None
        except (TypeError, ValueError):
            selected_project_id = None

        return render(request, self.template_name, self.get_context(request, form, selected_project_id))

class EntriesBase(LoginRequiredMixin, View):
    per_page_default = 25

    def _filtered_qs(self, request):
        qs = (TimeEntry.objects
              .filter(user=request.user)
              .select_related("project", "task"))
        q = (request.GET.get("q") or "").strip()
        proj = request.GET.get("project")
        dt_from = request.GET.get("from")
        dt_to = request.GET.get("to")

        if proj and proj.isdigit():
            qs = qs.filter(project_id=int(proj))
        if dt_from:
            qs = qs.filter(work_date__gte=dt_from)
        if dt_to:
            qs = qs.filter(work_date__lte=dt_to)
        if q:
            qs = qs.filter(
                models.Q(project__title__icontains=q) |
                models.Q(task__title__icontains=q) |
                models.Q(notes__icontains=q)
            )

        qs = qs.order_by("-work_date", "-created_at")
        return qs, {"q": q, "project_id": proj, "dt_from": dt_from, "dt_to": dt_to}

class EntriesFragmentView(EntriesBase):
    """Full panel with first page and a 'Load more' button."""
    template_name = "timetracking/partials/entries_panel.html"

    def get(self, request, *args, **kwargs):
        qs, params = self._filtered_qs(request)
        per_page = int(request.GET.get("per") or self.per_page_default)
        paginator = Paginator(qs, per_page)
        try:
            page_obj = paginator.page(int(request.GET.get("page") or 1))
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        ctx = {
            "entries": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            **params,
        }
        return render(request, self.template_name, ctx)

class EntriesRowsView(EntriesBase):
    """Returns only <tr> rows for appending when clicking 'Load more'."""
    template_name = "timetracking/partials/entries_rows.html"

    def get(self, request, *args, **kwargs):
        qs, _ = self._filtered_qs(request)
        per_page = int(request.GET.get("per") or self.per_page_default)
        paginator = Paginator(qs, per_page)
        try:
            page_obj = paginator.page(int(request.GET.get("page") or 1))
        except EmptyPage:
            # nothing more to load; return empty body
            return HttpResponse("")
        return render(request, self.template_name, {"entries": page_obj.object_list})


class EntryEditView(LoginRequiredMixin, View):
    """
    Modal edit for a single entry. GET -> form fragment, POST -> save and trigger entries refresh.
    """

    template_name = "timetracking/partials/entry_edit_form.html"

    def _get_entry(self, request, pk: int) -> TimeEntry:
        entry = get_object_or_404(TimeEntry.objects.select_related("project", "task"), pk=pk)
        # Basic rule: users can edit their own entries; expand later with PM overrides if desired.
        if entry.user_id != request.user.id and not request.user.is_superuser:
            raise PermissionError("Not allowed.")
        return entry

    def get(self, request, pk: int, *args, **kwargs):
        try:
            entry = self._get_entry(request, pk)
        except PermissionError:
            return HttpResponseBadRequest("Not allowed.")
        form = TimeEntryForm(instance=entry)
        return render(request, self.template_name, {"form": form, "entry": entry})

    def post(self, request, pk: int, *args, **kwargs):
        try:
            entry = self._get_entry(request, pk)
        except PermissionError:
            return HttpResponseBadRequest("Not allowed.")

        form = TimeEntryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            resp = HttpResponse(status=204)
            resp["HX-Trigger"] = "entriesChanged"
            return resp
        return render(request, self.template_name, {"form": form, "entry": entry}, status=400)

@method_decorator(require_GET, name="dispatch")
class ProjectOptionsView(LoginRequiredMixin, View):
    """
    Returns <option> list for the Project <select>, filtered by ?q=...
    If no TrackedProject rows exist yet, lazily hydrate from projects.Project.
    """
    template_name = "timetracking/partials/project_options.html"

    def get(self, request, *args, **kwargs):
        q = (request.GET.get("q") or "").strip()

        # Lazy hydrate once if mirror is empty
        if not TrackedProject.objects.exists():
            Project = django_apps.get_model("projects", "Project")
            from .signals import on_project_saved
            with transaction.atomic():
                for p in Project.objects.all().only("id", "title", "slug", "status"):
                    on_project_saved(Project, p)

        qs = TrackedProject.objects.all()
        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(slug__icontains=q) |
                Q(external_ref__icontains=q)
            )

        qs = qs.annotate(
            active_rank=Case(When(is_active=True, then=0), default=1, output_field=IntegerField()),
            prefix_rank=Case(
                When(title__istartswith=q, then=0) if q else When(pk__isnull=False, then=1),
                When(slug__istartswith=q, then=1) if q else When(pk__isnull=False, then=1),
                default=2,
                output_field=IntegerField(),
            ),
        ).order_by("active_rank", "prefix_rank", "title")[:RESULT_LIMIT]

        return render(request, self.template_name, {"projects": qs})


@method_decorator(require_GET, name="dispatch")
class TaskOptionsView(LoginRequiredMixin, View):
    """
    Returns <option> list for the Task <select>, filtered by ?q=... and scoped to ?project=<id>.
    Lazily hydrates TrackedTask for the chosen tracked project if none exist yet.
    """
    template_name = "timetracking/partials/task_options.html"

    def get(self, request, *args, **kwargs):
        project_id = request.GET.get("project")
        if not project_id or not project_id.isdigit():
            return HttpResponseBadRequest("Missing project id.")

        q = (request.GET.get("q") or "").strip()
        pid = int(project_id)

        qs = TrackedTask.objects.filter(project_id=pid)

        # Lazy hydrate if this tracked project has no mirrored tasks yet
        if not qs.exists():
            tp = TrackedProject.objects.filter(id=pid).only("id", "source_project_id").first()
            if tp and tp.source_project_id:
                Project = django_apps.get_model("projects", "Project")
                Task = django_apps.get_model("projects", "Task")
                from .signals import on_project_saved, on_task_saved
                parent = Project.objects.filter(pk=tp.source_project_id).first()
                if parent:
                    with transaction.atomic():
                        # Ensure project mirror up to date
                        on_project_saved(Project, parent)
                        # Mirror all tasks for that project
                        for t in Task.objects.filter(project_id=parent.pk).only("id", "title", "project_id"):
                            on_task_saved(Task, t)
                    qs = TrackedTask.objects.filter(project_id=pid)

        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(slug__icontains=q) |
                Q(external_ref__icontains=q)
            )

        qs = qs.annotate(
            active_rank=Case(When(is_active=True, then=0), default=1, output_field=IntegerField()),
            prefix_rank=Case(
                When(title__istartswith=q, then=0) if q else When(pk__isnull=False, then=1),
                When(slug__istartswith=q, then=1) if q else When(pk__isnull=False, then=1),
                default=2,
                output_field=IntegerField(),
            ),
        ).order_by("active_rank", "prefix_rank", "title")[:RESULT_LIMIT]

        return render(request, self.template_name, {"tasks": qs})

# ------------------------------
# Metrics helpers
# ------------------------------

def _safe_int(val, default=None):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default

def _default_range() -> Tuple[date, date]:
    today = date.today()
    return (today - timedelta(days=27), today)  # last 28 days

def _apply_filters(qs, user, project_id, d_from, d_to, bill):
    qs = qs.filter(user=user)
    if project_id:
        qs = qs.filter(project_id=project_id)
    if d_from:
        qs = qs.filter(work_date__gte=d_from)
    if d_to:
        qs = qs.filter(work_date__lte=d_to)
    if bill == "yes":
        qs = qs.filter(billable=True)
    elif bill == "no":
        qs = qs.filter(billable=False)
    return qs

def _fmt_hours(minutes: Optional[int]) -> float:
    return round((minutes or 0) / 60.0, 2)

def _percent(n: int, d: int) -> float:
    return round((n / d) * 100.0, 1) if d else 0.0

def _normalize_series(values: List[int]) -> List[int]:
    if not values:
        return []
    m = max(values)
    if m <= 0:
        return [0 for _ in values]
    return [int(round((v / m) * 100)) for v in values]


# ------------------------------
# Metrics views
# ------------------------------

class MetricsBase(LoginRequiredMixin, View):
    """
    Common parsing for filters + consistent queryset scoping.
    """

    def parse_params(self, request):
        pid = _safe_int(request.GET.get("project"))
        d_from = (request.GET.get("from") or "").strip()
        d_to = (request.GET.get("to") or "").strip()
        bill = (request.GET.get("bill") or "all").strip()          # all|yes|no
        interval = (request.GET.get("interval") or "week").strip() # day|week|month

        if not d_from or not d_to:
            df, dt = _default_range()
            d_from = d_from or df.isoformat()
            d_to = d_to or dt.isoformat()

        bill_flags = {
            "bill_all": bill == "all",
            "bill_yes": bill == "yes",
            "bill_no": bill == "no",
        }
        interval_flags = {
            "int_day": interval == "day",
            "int_week": interval == "week",
            "int_month": interval == "month",
        }

        return pid, d_from, d_to, bill, bill_flags, interval, interval_flags

    def filtered_qs(self, request):
        pid, d_from, d_to, bill, *_ = self.parse_params(request)
        qs = TimeEntry.objects.select_related("project", "task")
        return _apply_filters(qs, request.user, pid, d_from, d_to, bill)

    def _projects_for_filter(self, request, d_from: str, d_to: str) -> List[Dict[str, Any]]:
        rows = (
            TimeEntry.objects.filter(user=request.user, work_date__gte=d_from, work_date__lte=d_to)
            .values("project_id", "project__title")
            .annotate(total=Sum("duration_minutes"))
            .order_by("project__title")
        )
        return [{"id": r["project_id"], "title": r["project__title"]} for r in rows]


class MetricsHomeView(MetricsBase):
    template_name = "timetracking/metrics/home.html"

    def get(self, request, *args, **kwargs):
        pid, d_from, d_to, bill, bill_flags, interval, interval_flags = self.parse_params(request)

        projects = self._projects_for_filter(request, d_from, d_to)
        for p in projects:
            p["selected"] = (pid is not None and p["id"] == pid)

        # ---- user/role context (same pattern as TimeEntryView) ----
        profile = getattr(request.user, "profile", None)
        role_code = getattr(profile, "role", None)
        role_display = profile.get_role_display() if profile else "—"
        is_pm = bool(getattr(profile, "is_project_manager", False))
        is_dev = bool(getattr(profile, "is_developer", False))
        user_display_name = request.user.get_full_name() or request.user.get_username()

        ctx = {
            "projects": projects,
            "selected_project_id": pid,
            "from": d_from,
            "to": d_to,
            "bill": bill,
            **bill_flags,
            "interval": interval,
            **interval_flags,

            # expose to template
            "user_display_name": user_display_name,
            "user_role": role_code,
            "user_role_display": role_display,
            "is_pm": is_pm,
            "is_dev": is_dev,
            # convenience flag if you want to show PM-only UI bits
            "can_manage_metrics": is_pm,
        }
        return render(request, self.template_name, ctx)

class MetricsSummaryView(MetricsBase):
    template_name = "timetracking/metrics/_summary.html"

    def get(self, request, *args, **kwargs):
        qs = self.filtered_qs(request)

        agg = qs.aggregate(
            total=Sum("duration_minutes"),
            billable=Sum("duration_minutes", filter=Q(billable=True)),
            entries=Count("id"),
            first=Min("work_date"),
            last=Max("work_date"),
            days_active=Count("work_date", distinct=True),
        )
        total = agg["total"] or 0
        bill = agg["billable"] or 0
        nonbill = total - bill
        util = _percent(bill, total)
        avg_day = _fmt_hours(total) / (agg["days_active"] or 1)

        top_project = (
            qs.values("project_id", "project__title")
              .annotate(mins=Sum("duration_minutes"))
              .order_by("-mins")
              .first()
        )
        top_task = (
            qs.values("task_id", "task__title", "project__title")
              .annotate(mins=Sum("duration_minutes"))
              .order_by("-mins")
              .first()
        )

        ctx = {
            "k_total_hours": _fmt_hours(total),
            "k_billable_hours": _fmt_hours(bill),
            "k_nonbillable_hours": _fmt_hours(nonbill),
            "k_util": util,
            "k_entries": agg["entries"] or 0,
            "k_days": agg["days_active"] or 0,
            "k_avg_day": round(avg_day, 2),
            "first_date": agg["first"],
            "last_date": agg["last"],
            "top_project": top_project,
            "top_task": top_task,
        }
        return render(request, self.template_name, ctx)


class MetricsTableView(MetricsBase):
    def get(self, request, kind: str, *args, **kwargs):
        if kind not in ("projects", "tasks"):
            return HttpResponseBadRequest("Invalid table kind.")

        qs = self.filtered_qs(request)

        # Local table controls
        q = (request.GET.get("q") or "").strip()
        top = _safe_int(request.GET.get("top"), 20)
        sort = (request.GET.get("sort") or "-hours").strip()  # "-hours", "billable", etc.

        # Simple search
        if q:
            if kind == "projects":
                qs = qs.filter(project__title__icontains=q)
            else:
                qs = qs.filter(Q(task__title__icontains=q) | Q(project__title__icontains=q))

        # sort helpers
        def next_sort_for(key: str, current: str) -> str:
            if current == key:
                return f"-{key}"
            if current == f"-{key}":
                return key
            return f"-{key}"

        def dir_for(key: str, current: str) -> Optional[str]:
            if current == key:
                return "asc"
            if current == f"-{key}":
                return "desc"
            return None

        if kind == "projects":
            rows_qs = (
                qs.values("project_id", "project__title")
                  .annotate(
                      minutes=Sum("duration_minutes"),
                      billable=Sum("duration_minutes", filter=Q(billable=True)),
                      entries=Count("id"),
                      tasks=Count("task", distinct=True),
                      first=Min("work_date"),
                      last=Max("work_date"),
                  )
            )
            order_map = {
                "hours": "minutes", "-hours": "-minutes",
                "billable": "billable", "-billable": "-billable",
                "entries": "entries", "-entries": "-entries",
                "first": "first", "-first": "-first",
                "last": "last", "-last": "-last",
                "project": "project__title", "-project": "-project__title",
            }
            rows_qs = rows_qs.order_by(order_map.get(sort, "-minutes"), "project__title")[: top or 20]
            rows = [{
                "id": r["project_id"],
                "label": r["project__title"],
                "hours": _fmt_hours(r["minutes"] or 0),
                "billable": _fmt_hours(r["billable"] or 0),
                "entries": r["entries"] or 0,
                "tasks": r["tasks"] or 0,
                "first": r["first"],
                "last": r["last"],
            } for r in rows_qs]
            keys = ["project", "hours", "billable", "entries", "tasks", "first", "last"]
            title = "By Project"
            template = "timetracking/metrics/_table_projects.html"
        else:
            rows_qs = (
                qs.values("task_id", "task__title", "project__title", "project_id")
                  .annotate(
                      minutes=Sum("duration_minutes"),
                      billable=Sum("duration_minutes", filter=Q(billable=True)),
                      entries=Count("id"),
                      first=Min("work_date"),
                      last=Max("work_date"),
                  )
            )
            order_map = {
                "hours": "minutes", "-hours": "-minutes",
                "billable": "billable", "-billable": "-billable",
                "entries": "entries", "-entries": "-entries",
                "first": "first", "-first": "-first",
                "last": "last", "-last": "-last",
                "task": "task__title", "-task": "-task__title",
                "project": "project__title", "-project": "-project__title",
            }
            rows_qs = rows_qs.order_by(order_map.get(sort, "-minutes"), "project__title", "task__title")[: top or 20]
            rows = [{
                "label": r["task__title"],
                "project": r["project__title"],
                "project_id": r["project_id"],
                "hours": _fmt_hours(r["minutes"] or 0),
                "billable": _fmt_hours(r["billable"] or 0),
                "entries": r["entries"] or 0,
                "first": r["first"],
                "last": r["last"],
            } for r in rows_qs]
            keys = ["task", "project", "hours", "billable", "entries", "first", "last"]
            title = "By Task"
            template = "timetracking/metrics/_table_tasks.html"

        sort_states = {k: {"next": next_sort_for(k, sort), "dir": dir_for(k, sort)} for k in keys}
        top_options = [{"value": n, "label": f"Top {n}", "selected": (n == (top or 20))}
                       for n in (10, 20, 50, 100, 200)]

        ctx = {
            "kind": kind,
            "title": title,
            "rows": rows,
            "q": q,
            "sort": sort,
            "top": top,
            "top_options": top_options,
            "sort_states": sort_states,
        }
        return render(request, template, ctx)

class MetricsTrendView(MetricsBase):
    template_name = "timetracking/metrics/_trend.html"

    def get(self, request, *args, **kwargs):
        qs = self.filtered_qs(request)
        _, d_from, d_to, _, _, interval, _ = self.parse_params(request)

        if interval == "day":
            trunc = TruncDate("work_date")
            fmt = "%Y-%m-%d"
        elif interval == "month":
            trunc = TruncMonth("work_date")
            fmt = "%Y-%m"
        else:
            trunc = TruncWeek("work_date")
            fmt = "%Y-W%W"

        buckets = (
            qs.annotate(period=trunc)
              .values("period")
              .annotate(
                  minutes=Sum("duration_minutes"),
                  billable=Sum("duration_minutes", filter=Q(billable=True)),
                  entries=Count("id"),
              )
              .order_by("period")
        )

        series_abs = [int(b["minutes"] or 0) for b in buckets]
        series_pct = _normalize_series(series_abs)

        rows = [{
            "period": b["period"].strftime(fmt) if hasattr(b["period"], "strftime") else str(b["period"]),
            "hours": _fmt_hours(b["minutes"]),
            "billable": _fmt_hours(b["billable"] or 0),
            "entries": b["entries"],
        } for b in buckets]

        ctx = {
            "series_pct": series_pct,
            "series_len": len(series_pct),
            "rows": rows,
            "interval": interval,
            "from": d_from,
            "to": d_to,
        }
        return render(request, self.template_name, ctx)
