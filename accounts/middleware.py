from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

class AppLoginRequiredMiddleware(MiddlewareMixin):
    """
    Require authentication for all routes under /app/**, with small allow-list.
    Redirects browsers to LOGIN_URL with ?next=...; returns 401 JSON for API-ish requests.
    """
    APP_PREFIX = "/app/"
    ALLOW_PATHS = {}

    def process_request(self, request):
        # If AuthenticationMiddleware hasn't run, fail open to avoid attribute errors.
        if not hasattr(request, "user"):
            return

        path = request.path_info  # normalized, no script-prefix
        if not path.startswith(self.APP_PREFIX):
            return  # only guard /app/**
        if path in self.ALLOW_PATHS:
            return  # allow-listed

        if request.user.is_authenticated:
            return

        # Prefer JSON 401 for API/XHR; otherwise redirect to login with full path (incl. query).
        accepts_json = "application/json" in request.headers.get("Accept", "")
        is_htmx = request.headers.get("HX-Request") == "true"
        if accepts_json and not is_htmx:
            return JsonResponse({"detail": "Authentication required."}, status=401)

        next_url = request.get_full_path()
        return redirect(f"{settings.LOGIN_URL}?next={next_url}")
