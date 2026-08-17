"""CSRF failure responses — JSON for API paths, HTML for classic pages."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse


def csrf_failure(
    request: HttpRequest, reason: str = ""
) -> HttpResponse:
    path = request.path or ""
    if path.startswith("/api/"):
        return JsonResponse(
            {
                "ok": False,
                "error": "csrf_failed",
                "message": reason or "csrf_failed",
            },
            status=403,
        )
    from django.views.csrf import csrf_failure as django_csrf_failure

    return django_csrf_failure(request, reason=reason)
