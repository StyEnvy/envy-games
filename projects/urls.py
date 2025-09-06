from django.urls import path
from . import views

app_name = "projects"

urlpatterns = [
    # Home / lists
    path("", views.ProjectListView.as_view(), name="list"),
    path("mine/", views.ProjectListMineView.as_view(), name="list_mine"),
    path("all/", views.ProjectListAllView.as_view(), name="list_all"),

    # Project views
    path("new/", views.ProjectCreateView.as_view(), name="create"),
    path("<slug:slug>/", views.ProjectDetailView.as_view(), name="detail"),
    path("<slug:slug>/edit/", views.ProjectUpdateView.as_view(), name="edit"),

    # Board views
    path("<slug:slug>/board/", views.board_view, name="board"),
    path("<slug:slug>/roadmap/", views.roadmap_view, name="roadmap"),

    # Member management
    path("<slug:slug>/members/add/", views.add_member, name="add_member"),
    path("<slug:slug>/members/<int:user_id>/remove/", views.remove_member, name="remove_member"),

    # HTMX endpoints
    path("htmx/task/<int:task_id>/move/", views.move_task, name="move_task"),
    path("htmx/column/<int:column_id>/add-task/", views.quick_add_task, name="quick_add_task"),
    path("htmx/task/<int:task_id>/modal/", views.task_modal, name="task_modal"),
    path("htmx/task/<int:task_id>/convert/", views.convert_to_task, name="convert_to_task"),
    path("htmx/task/<int:task_id>/upload/", views.upload_attachment, name="upload_attachment"),
]
