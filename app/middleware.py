"""未ログイン時はログイン画面を入口にし、閲覧モード選択後のみサイトを開ける。"""

from __future__ import annotations

from urllib.parse import quote

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from .browse_mode_services import (
    BROWSE_MODE_SESSION_KEY,
    clear_browse_mode,
    is_browse_mode,
    path_allows_without_browse_mode,
    path_denies_student_data_in_browse_mode,
    unauthorized_json_response,
)


class BrowseModeGateMiddleware:
    """
    未ログインかつ閲覧モード未選択のアクセスを /login/ へ誘導する。
    ログイン済み・許可パスはそのまま通す。
    閲覧モード中は SPA/HTML シェルを通すが、学生データ API は 401 にする。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not getattr(settings, "BROWSE_MODE_GATE_ENABLED", True):
            request.is_browse_mode = False
            return self.get_response(request)

        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            if request.session.get(BROWSE_MODE_SESSION_KEY):
                clear_browse_mode(request)
            request.is_browse_mode = False
            return self.get_response(request)

        path = request.path or "/"
        if path_allows_without_browse_mode(path):
            request.is_browse_mode = is_browse_mode(request)
            return self.get_response(request)

        if is_browse_mode(request):
            request.is_browse_mode = True
            if path_denies_student_data_in_browse_mode(path):
                return unauthorized_json_response()
            return self.get_response(request)

        request.is_browse_mode = False
        # SPA JSON APIs must not receive HTML login redirects
        if (request.path or "").startswith("/api/v1/"):
            return unauthorized_json_response()
        if getattr(settings, "WASE_REACT_SPA", False):
            login_url = "/app/login"
        else:
            login_url = reverse("login")
        next_path = request.get_full_path() or "/"
        if next_path.startswith(login_url) or next_path.startswith("/login"):
            return redirect(login_url)
        return redirect(f"{login_url}?next={quote(next_path, safe='/?&=')}")
