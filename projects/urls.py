from django.urls import path
from . import views

app_name = "projects"

urlpatterns = [
    path("", views.ProjectHomeView.as_view(), name="home"),
    path("mine/", views.ProjectListView.as_view(scope="mine"), name="list_mine"),
    path("all/", views.ProjectListView.as_view(scope="all"), name="list_all"),
    path("new/", views.ProjectCreateView.as_view(), name="create"),
    path("<slug:slug>/", views.ProjectDetailView.as_view(), name="detail"),
    path("<slug:slug>/edit/", views.ProjectUpdateView.as_view(), name="edit"),  # ← NEW
]
