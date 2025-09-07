from django.urls import path

from .views import (
    ProjectListCreateView, ProjectUpdateView,
    TaskListCreateView, TaskUpdateView,
    EntryListView, EntryCreateView, EntryUpdateView, EntryDeleteView,
    weekly_report, weekly_report_csv,
)

app_name = "timetracking"

urlpatterns = [
    # projects
    path("projects/", ProjectListCreateView.as_view(), name="project_list"),
    path("projects/<int:pk>/edit/", ProjectUpdateView.as_view(), name="project_edit"),

    # tasks
    path("projects/<int:project_id>/tasks/", TaskListCreateView.as_view(), name="task_list"),
    path("tasks/<int:pk>/edit/", TaskUpdateView.as_view(), name="task_edit"),

    # entries
    path("entries/", EntryListView.as_view(), name="entry_list"),
    path("entries/new/", EntryCreateView.as_view(), name="entry_create"),
    path("entries/<int:pk>/edit/", EntryUpdateView.as_view(), name="entry_edit"),
    path("entries/<int:pk>/delete/", EntryDeleteView.as_view(), name="entry_delete"),

    # reports
    path("reports/weekly/", weekly_report, name="weekly_report"),
    path("reports/weekly.csv", weekly_report_csv, name="weekly_report_csv"),
]