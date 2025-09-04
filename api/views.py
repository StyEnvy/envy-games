from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.db import transaction
from tasks.models import Board, Column, Task
from projects.models import Project

@login_required
def create_column(request, board_id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    board = get_object_or_404(Board, id=board_id)
    name = request.POST.get("name", "").strip() or "New Column"
    max_order = board.columns.aggregate(m=models.Max("order"))["m"] or 0
    col = Column.objects.create(board=board, name=name, order=(max_order + 1024))
    return JsonResponse({"id": col.id, "name": col.name, "order": col.order})

@login_required
def create_card(request, column_id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    col = get_object_or_404(Column, id=column_id)
    board = col.board
    title = request.POST.get("title", "").strip() or "New Card"
    kind = request.POST.get("kind", "task")
    max_order = col.tasks.aggregate(m=models.Max("order"))["m"] or 0
    payload = dict(
        project=board.project, board=board, column=col,
        kind=kind, title=title, created_by=request.user, order=(max_order + 1024)
    )
    if kind == "task":
        payload.update(status="todo", priority=3)
    else:
        payload.update(impact=3, confidence=3, ease=3)
    t = Task.objects.create(**payload)
    return JsonResponse({"id": t.id, "title": t.title, "kind": t.kind, "order": t.order})

@login_required
def edit_card(request, task_id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    t = get_object_or_404(Task, id=task_id)
    title = request.POST.get("title")
    desc = request.POST.get("description")
    if title is not None:
        t.title = title.strip()
    if desc is not None:
        t.description = desc
    if t.kind == "task":
        status = request.POST.get("status")
        priority = request.POST.get("priority")
        if status: t.status = status
        if priority: t.priority = int(priority)
    if t.kind == "idea":
        for k in ("impact", "confidence", "ease"):
            v = request.POST.get(k)
            if v: setattr(t, k, int(v))
    t.full_clean()
    t.save()
    return JsonResponse({"ok": True})

@login_required
def move_card(request, task_id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    t = get_object_or_404(Task, id=task_id)
    target_column_id = int(request.POST.get("column_id"))
    new_order = int(request.POST.get("order", t.order))
    target_col = get_object_or_404(Column, id=target_column_id)
    # WIP check
    if target_col.wip_limit:
        if target_col.tasks.exclude(id=t.id).count() >= target_col.wip_limit:
            return JsonResponse({"ok": False, "error": "WIP limit exceeded"}, status=422)
    # Same-board only
    if target_col.board_id != t.board_id:
        return JsonResponse({"ok": False, "error": "Cross-board drag disabled"}, status=422)
    with transaction.atomic():
        t.column = target_col
        t.order = new_order
        t.full_clean()
        t.save()
    return JsonResponse({"ok": True})

@login_required
def convert_card(request, task_id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    t = get_object_or_404(Task, id=task_id)
    if t.kind == "task":
        t.kind = "idea"
        t.status = ""
        t.priority = None
        t.impact = t.impact or 3
        t.confidence = t.confidence or 3
        t.ease = t.ease or 3
    else:
        t.kind = "task"
        t.status = t.status or "todo"
        t.priority = t.priority or 3
        t.impact = t.confidence = t.ease = None
        t.score = 0
    t.full_clean()
    t.save()
    return JsonResponse({"ok": True, "kind": t.kind})