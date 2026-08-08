"""SPA / API helpers in middleware (Phase 10 prep — no classic breakage)."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse


def _is_api_v1(path: str) -> bool:
    return (path or "").startswith("/api/v1/")


def _is_login_redirect(location: str) -> bool:
    loc = (location or "").lower()
    return "/login" in loc


class ApiV1UnauthorizedJsonMiddleware:
    """
    Convert HTML login redirects on /api/v1/* into JSON 401.

    Covers:
    - @login_required redirect responses
    - BrowseModeGateMiddleware redirect when gate blocks an API path

    Does not change classic HTML page auth flows.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        path = request.path or "/"
        if _is_api_v1(path):
            # Intercept browse-gate / other early redirects by wrapping get_response
            # BrowseModeGate runs before this middleware if ordered after it —
            # we must run AFTER BrowseModeGate so we convert its redirects.
            response = self.get_response(request)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.get("Location", "")
                if _is_login_redirect(location):
                    return JsonResponse(
                        {
                            "ok": False,
                            "error": "unauthorized",
                            "message": "authentication_required",
                        },
                        status=401,
                    )
            return response
        return self.get_response(request)
