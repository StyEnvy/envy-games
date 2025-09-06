from django.urls import reverse_lazy
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponseForbidden
from django.core.exceptions import PermissionDenied

from .forms import LoginForm
from .models import UserRole


class LoginView(auth_views.LoginView):
    template_name = "registration/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    next_page = reverse_lazy("public:home")


# ----- Role utilities -----

def user_has_role(user, *roles: UserRole) -> bool:
    """
    True if authenticated user has a profile and role in the provided set.
    """
    if not user.is_authenticated:
        return False
    profile = getattr(user, "profile", None)
    return bool(profile and profile.role in roles)


def role_required(*roles: UserRole):
    """
    Decorator for FBVs. Example:
        @role_required(UserRole.PROJECT_MANAGER)
        def my_view(request): ...
    """
    def decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            if user_has_role(request.user, *roles):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return _wrapped
    return decorator


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Mixin for CBVs. Example:
        class PMOnlyView(RoleRequiredMixin, View):
            required_roles = (UserRole.PROJECT_MANAGER,)
    """
    required_roles: tuple[UserRole, ...] = ()

    def test_func(self):
        return user_has_role(self.request.user, *self.required_roles)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        return HttpResponseForbidden("You do not have permission to access this page.")
