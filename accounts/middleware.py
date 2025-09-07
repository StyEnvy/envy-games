from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

class AppLoginRequiredMiddleware(MiddlewareMixin):
    """
    Require authentication for all routes under APP_PREFIX (default: /app/),
    with allow-listed paths/prefixes from settings. For API/XHR requests,
    return JSON 401; otherwise redirect to LOGIN_URL with ?next=...
    """
    APP_PREFIX = getattr(settings, "APP_LOGIN_PREFIX", "/app/")
    ALLOW_PATHS = frozenset(getattr(settings, "APP_LOGIN_ALLOW_PATHS", ()))
    ALLOW_PREFIXES = tuple(getattr(settings, "APP_LOGIN_ALLOW_PREFIXES", ()))

    def process_request(self, request):
        # If AuthenticationMiddleware hasn't run, fail open
        if not hasattr(request, "user"):
            return

        path = request.path_info  # normalized, no script-prefix
        if not path.startswith(self.APP_PREFIX):
            return

        if path in self.ALLOW_PATHS or any(path.startswith(pfx) for pfx in self.ALLOW_PREFIXES):
            return

        if request.user.is_authenticated:
            return

        # Prefer JSON for API/XHR unless it's HTMX (which expects HTML)
        accepts_json = "application/json" in (request.headers.get("Accept") or "")
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        is_htmx = request.headers.get("HX-Request") == "true"
        if (accepts_json or is_ajax) and not is_htmx:
            return JsonResponse({"detail": "Authentication required."}, status=401)

        next_url = request.get_full_path()
        return redirect(f"{settings.LOGIN_URL}?next={next_url}")
