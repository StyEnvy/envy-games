from django.urls import path
from .views import (
    TimeEntryView, EntriesFragmentView, EntryEditView,
    ProjectOptionsView, TaskOptionsView,
    EntriesRowsView,
    MetricsHomeView, MetricsSummaryView, MetricsTableView, MetricsTrendView,
)

app_name = "timetracking"

urlpatterns = [
    path("time/", TimeEntryView.as_view(), name="home"),
    path("time/entries/fragment/", EntriesFragmentView.as_view(), name="entries_fragment"),
    path("time/entries/rows/", EntriesRowsView.as_view(), name="entries_rows"),
    path("time/entry/<int:pk>/edit/", EntryEditView.as_view(), name="entry_edit"),
    path("time/options/projects/", ProjectOptionsView.as_view(), name="project_options"),
    path("time/options/tasks/", TaskOptionsView.as_view(), name="task_options"),
    # --- METRICS ---
    path("time/metrics/", MetricsHomeView.as_view(), name="metrics_home"),
    path("time/metrics/summary/", MetricsSummaryView.as_view(), name="metrics_summary"),
    path("time/metrics/table/<str:kind>/", MetricsTableView.as_view(), name="metrics_table"),
    path("time/metrics/trend/", MetricsTrendView.as_view(), name="metrics_trend"),
]
