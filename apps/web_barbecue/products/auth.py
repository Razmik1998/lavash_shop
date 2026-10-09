"""API-key authentication for machine-to-machine endpoints.

Used only by the Admin -> Django product sync endpoint, which has no
session/cookie-based auth of its own.
"""
from functools import wraps

from django.conf import settings
from django.http import JsonResponse


def require_api_key(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        key = request.headers.get("X-API-Key")
        if not key:
            return JsonResponse({"error": "missing_api_key"}, status=401)
        if key != settings.WEB_SYNC_API_KEY:
            return JsonResponse({"error": "invalid_api_key"}, status=403)
        return view_func(request, *args, **kwargs)

    return wrapper
