from django.urls import path
from django.http import HttpResponse
urlpatterns = [
    path("", lambda r: HttpResponse("Assets catalog — build me!"), name="assets_index"),
]
