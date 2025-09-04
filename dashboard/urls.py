from django.urls import path
from .views import app_home

app_name = "dashboard"
urlpatterns = [
    path("", app_home, name="home"),
]