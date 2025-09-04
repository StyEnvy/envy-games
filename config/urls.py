from django.contrib import admin
from django.urls import path, include
from accounts import views as account_views

urlpatterns = [
    path("admin/", admin.site.urls),

    # Public site
    path("", include("public.urls")),

    # Our auth views (override defaults)
    path("login/",  account_views.LoginView.as_view(),  name="login"),
    path("logout/", account_views.LogoutView.as_view(), name="logout"),
    path("password_reset/", account_views.PasswordResetView.as_view(), name="password_reset"),
    path("password_reset/done/", account_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", account_views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset/done/", account_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("password_change/", account_views.PasswordChangeView.as_view(), name="password_change"),
    path("password_change/done/", account_views.PasswordChangeDoneView.as_view(), name="password_change_done"),

    # Django stock auth utility URLs (password reset templates, etc.) under /accounts/
    path("accounts/", include("django.contrib.auth.urls")),

    # Internal app
    path("app/dashboard/", include("dashboard.urls")),
    path("app/projects/", include("projects.urls")),
    path("app/tasks/", include("tasks.urls")),
    path("app/api/", include("api.urls")),
    path("accounts/", include("accounts.urls")),
]
