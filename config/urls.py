from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts import views as account_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # Public site
    path("", include("public.urls")),

    # Authentication (minimal - just login/logout)
    path("login/", account_views.LoginView.as_view(), name="login"),
    path("logout/", account_views.LogoutView.as_view(), name="logout"),

    # Internal app (protected by middleware)
    path("app/dashboard/", include("dashboard.urls")),
    path("app/projects/", include("projects.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)