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

    def form_valid(self, form):
        response = super().form_valid(form)
        # If user didn't opt into "remember me", expire at browser close
        if not form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(0)
        return response

class LogoutView(auth_views.LogoutView):
    next_page = reverse_lazy("public:home")

# ----- Role utilities -----
def user_has_role(user, *roles: UserRole) -> bool:
    if not user.is_authenticated:
        return False
    profile = getattr(user, "profile", None)
    return bool(profile and profile.role in roles)

def role_required(*roles: UserRole):
    def decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            if user_has_role(request.user, *roles):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return _wrapped
    return decorator

class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    required_roles: tuple[UserRole, ...] = ()
    def test_func(self):
        return user_has_role(self.request.user, *self.required_roles)
    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        return HttpResponseForbidden("You do not have permission to access this page.")
