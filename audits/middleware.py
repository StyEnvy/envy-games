import threading

_thread_locals = threading.local()

def set_current_request(request):
    _thread_locals.request = request

def get_current_request():
    return getattr(_thread_locals, "request", None)

def get_current_user():
    req = get_current_request()
    return getattr(req, "user", None) if req else None

class AuditRequestMiddleware:
    """Stores the current request on a thread-local so audit logs can include user/IP/UA."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_request(request)
        try:
            return self.get_response(request)
        finally:
            set_current_request(None)
