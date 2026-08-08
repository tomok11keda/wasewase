"""Auth helpers for React SPA JSON API — wraps existing forms/OTP/session."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.http import HttpRequest
from django.utils.http import url_has_allowed_host_and_scheme

from .browse_mode_services import clear_browse_mode, enable_browse_mode, is_browse_mode
from .constants import FACULTY_CHOICES
from .forms import (
    EmailAuthenticationForm,
    PasswordResetOTPVerifyForm,
    PasswordResetRequestForm,
    PasswordResetSetForm,
    SignUpForm,
    SignupOTPVerifyForm,
)
from .models import User, UserProfile
from .otp_services import (
    PASSWORD_RESET_USER_SESSION_KEY,
    PASSWORD_RESET_VERIFIED_SESSION_KEY,
    SIGNUP_PENDING_SESSION_KEY,
    EmailConfigurationError,
    clear_password_reset_session,
    create_and_send_password_reset_otp,
    create_and_send_signup_otp,
    get_email_config_errors,
    verify_password_reset_otp,
    verify_signup_otp,
)
from .inbox_services import get_unread_inbox_message_count
from .notification_services import get_unread_notification_count
from .spa_views import _avatar_url, _display_name, _initial


def form_field_errors(form) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for field, errors in form.errors.items():
        out[field] = [str(e) for e in errors]
    return out


def safe_next_url(request: HttpRequest, raw: str | None, *, default: str = "/app/") -> str:
    next_url = (raw or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return default


def serialize_me(request: HttpRequest) -> dict[str, Any]:
    user = request.user
    authenticated = bool(getattr(user, "is_authenticated", False))
    payload: dict[str, Any] = {
        "authenticated": authenticated,
        "is_browse_mode": is_browse_mode(request),
        "react_spa_enabled": bool(getattr(settings, "WASE_REACT_SPA", False)),
        "user": None,
        "pending_signup": bool(request.session.get(SIGNUP_PENDING_SESSION_KEY)),
        "pending_password_reset": bool(
            request.session.get(PASSWORD_RESET_USER_SESSION_KEY)
        ),
        "password_reset_verified": bool(
            request.session.get(PASSWORD_RESET_VERIFIED_SESSION_KEY)
        ),
    }
    if authenticated:
        payload["user"] = {
            "id": user.pk,
            "email": user.email,
            "username": user.get_username(),
            "display_name": _display_name(user),
            "avatar_url": _avatar_url(user),
            "initial": _initial(user),
        }
        payload["unread_notifications"] = get_unread_notification_count(user)
        try:
            payload["dm_unread_total"] = int(
                get_unread_inbox_message_count(user) or 0
            )
        except Exception:
            payload["dm_unread_total"] = 0
    else:
        payload["unread_notifications"] = 0
        payload["dm_unread_total"] = 0
    return payload


def signup_meta() -> dict[str, Any]:
    return {
        "ok": True,
        "faculties": [{"value": v, "label": label} for v, label in FACULTY_CHOICES],
        "email_console_fallback": bool(
            getattr(settings, "EMAIL_USE_CONSOLE_FALLBACK", False)
        ),
        "email_config_errors": get_email_config_errors(),
    }


def _persist_signup_user(form: SignUpForm) -> AbstractBaseUser:
    email = form.cleaned_data["email"]
    faculty = form.cleaned_data["faculty"]
    password = form.cleaned_data["password1"]
    nickname = form.cleaned_data["nickname"]

    pending = User.objects.filter(email__iexact=email, is_active=False).first()
    if pending:
        pending.set_password(password)
        pending.save(update_fields=["password"])
        user = pending
    else:
        user = form.save()

    UserProfile.objects.update_or_create(
        user=user,
        defaults={
            "department": faculty,
            "name": nickname,
            "terms_accepted": True,
        },
    )
    return user


def _pending_signup_user(request: HttpRequest) -> AbstractBaseUser | None:
    user_id = request.session.get(SIGNUP_PENDING_SESSION_KEY)
    if not user_id:
        return None
    return User.objects.filter(pk=user_id, is_active=False).first()


def _password_reset_user(request: HttpRequest) -> AbstractBaseUser | None:
    user_id = request.session.get(PASSWORD_RESET_USER_SESSION_KEY)
    if not user_id:
        return None
    return User.objects.filter(pk=user_id, is_active=True).first()


def login_with_form(request: HttpRequest, data: dict) -> tuple[dict, int]:
    if request.user.is_authenticated and request.user.is_active:
        return (
            {
                "ok": True,
                "already_authenticated": True,
                "redirect": safe_next_url(request, data.get("next")),
                "me": serialize_me(request),
            },
            200,
        )
    form = EmailAuthenticationForm(
        request,
        data={
            "username": data.get("email") or data.get("username") or "",
            "password": data.get("password") or "",
        },
    )
    if not form.is_valid():
        return (
            {
                "ok": False,
                "error": "invalid_credentials",
                "errors": form_field_errors(form),
                "message": "メールアドレスまたはパスワードが正しくありません。",
            },
            400,
        )
    user = form.get_user()
    login(request, user)
    clear_browse_mode(request)
    return (
        {
            "ok": True,
            "redirect": safe_next_url(request, data.get("next")),
            "me": serialize_me(request),
        },
        200,
    )


def logout_session(request: HttpRequest) -> dict[str, Any]:
    logout(request)
    return {"ok": True, "redirect": "/app/login"}


def enter_browse(request: HttpRequest, next_url: str | None) -> dict[str, Any]:
    if request.user.is_authenticated:
        return {"ok": True, "redirect": "/app/", "authenticated": True}
    enable_browse_mode(request)
    return {
        "ok": True,
        "redirect": safe_next_url(request, next_url, default="/app/"),
        "me": serialize_me(request),
    }


def signup_with_form(request: HttpRequest, data: dict) -> tuple[dict, int]:
    if request.user.is_authenticated and request.user.is_active:
        return (
            {"ok": True, "already_authenticated": True, "redirect": "/app/"},
            200,
        )
    form = SignUpForm(
        {
            "email": data.get("email") or "",
            "nickname": data.get("nickname") or "",
            "faculty": data.get("faculty") or "",
            "password1": data.get("password1") or "",
            "password2": data.get("password2") or "",
            "accept_terms": data.get("accept_terms")
            in (True, "true", "True", "1", "on", 1),
        }
    )
    if not form.is_valid():
        return (
            {
                "ok": False,
                "error": "validation",
                "errors": form_field_errors(form),
                "message": "入力内容を確認してください。",
            },
            400,
        )
    try:
        with transaction.atomic():
            user = _persist_signup_user(form)
            create_and_send_signup_otp(user)
    except EmailConfigurationError as exc:
        return (
            {"ok": False, "error": "email_config", "message": str(exc)},
            503,
        )
    except Exception:
        return (
            {
                "ok": False,
                "error": "email_send_failed",
                "message": "認証メールの送信に失敗しました。",
            },
            500,
        )
    request.session[SIGNUP_PENDING_SESSION_KEY] = user.pk
    request.session.modified = True
    console = bool(getattr(settings, "EMAIL_USE_CONSOLE_FALLBACK", False))
    return (
        {
            "ok": True,
            "redirect": "/app/verify",
            "masked_email": user.email,
            "console_fallback": console,
            "message": (
                "開発モード: 認証コードはサーバーのターミナルに出力されています。"
                if console
                else f"{user.email} に6桁の認証コードを送信しました。"
            ),
        },
        201,
    )


def verify_signup(request: HttpRequest, data: dict) -> tuple[dict, int]:
    user = _pending_signup_user(request)
    if not user:
        return (
            {
                "ok": False,
                "error": "no_pending",
                "message": "新規登録からやり直してください。",
                "redirect": "/app/signup",
            },
            400,
        )
    form = SignupOTPVerifyForm({"code": data.get("code") or ""})
    if not form.is_valid():
        return (
            {
                "ok": False,
                "error": "validation",
                "errors": form_field_errors(form),
                "masked_email": user.email,
            },
            400,
        )
    error = verify_signup_otp(user, form.cleaned_data["code"])
    if error:
        return (
            {
                "ok": False,
                "error": "invalid_code",
                "message": error,
                "masked_email": user.email,
            },
            400,
        )
    user.is_active = True
    user.save(update_fields=["is_active"])
    del request.session[SIGNUP_PENDING_SESSION_KEY]
    login(request, user)
    clear_browse_mode(request)
    return (
        {
            "ok": True,
            "redirect": "/app/?login_success=1",
            "me": serialize_me(request),
            "message": "メール認証が完了しました。ようこそ、わせわせへ！",
        },
        200,
    )


def resend_signup_otp(request: HttpRequest) -> tuple[dict, int]:
    user = _pending_signup_user(request)
    if not user:
        return (
            {
                "ok": False,
                "error": "no_pending",
                "message": "新規登録からやり直してください。",
                "redirect": "/app/signup",
            },
            400,
        )
    try:
        create_and_send_signup_otp(user)
    except EmailConfigurationError as exc:
        return ({"ok": False, "error": "email_config", "message": str(exc)}, 503)
    except Exception:
        return (
            {
                "ok": False,
                "error": "email_send_failed",
                "message": "認証メールの送信に失敗しました。",
            },
            500,
        )
    return (
        {
            "ok": True,
            "message": "認証コードを再送信しました。",
            "masked_email": user.email,
        },
        200,
    )


def password_reset_request(request: HttpRequest, data: dict) -> tuple[dict, int]:
    form = PasswordResetRequestForm({"email": data.get("email") or ""})
    if not form.is_valid():
        return (
            {
                "ok": False,
                "error": "validation",
                "errors": form_field_errors(form),
            },
            400,
        )
    email = form.cleaned_data["email"]
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        return (
            {
                "ok": False,
                "error": "not_found",
                "errors": {"email": ["このメールアドレスは登録されていません。"]},
                "message": "このメールアドレスは登録されていません。",
            },
            400,
        )
    if not user.is_active:
        return (
            {
                "ok": False,
                "error": "inactive",
                "message": "このアカウントはまだメール認証が完了していません。",
                "redirect": "/app/signup",
            },
            400,
        )
    try:
        create_and_send_password_reset_otp(user)
    except EmailConfigurationError as exc:
        return ({"ok": False, "error": "email_config", "message": str(exc)}, 503)
    except Exception:
        return (
            {
                "ok": False,
                "error": "email_send_failed",
                "message": "確認メールの送信に失敗しました。",
            },
            500,
        )
    clear_password_reset_session(request)
    request.session[PASSWORD_RESET_USER_SESSION_KEY] = user.pk
    request.session.modified = True
    console = bool(getattr(settings, "EMAIL_USE_CONSOLE_FALLBACK", False))
    return (
        {
            "ok": True,
            "redirect": "/app/password-reset/verify",
            "masked_email": user.email,
            "console_fallback": console,
            "message": (
                "開発モード: 確認コードはサーバーのターミナルに出力されています。"
                if console
                else f"{user.email} に6桁の確認コードを送信しました。"
            ),
        },
        200,
    )


def password_reset_verify(request: HttpRequest, data: dict) -> tuple[dict, int]:
    user = _password_reset_user(request)
    if not user:
        return (
            {
                "ok": False,
                "error": "no_pending",
                "message": "パスワード再設定はメールアドレスの入力からやり直してください。",
                "redirect": "/app/password-reset",
            },
            400,
        )
    if request.session.get(PASSWORD_RESET_VERIFIED_SESSION_KEY):
        return (
            {"ok": True, "already_verified": True, "redirect": "/app/password-reset/set"},
            200,
        )
    form = PasswordResetOTPVerifyForm({"code": data.get("code") or ""})
    if not form.is_valid():
        return (
            {
                "ok": False,
                "error": "validation",
                "errors": form_field_errors(form),
                "masked_email": user.email,
            },
            400,
        )
    error = verify_password_reset_otp(user, form.cleaned_data["code"])
    if error:
        return (
            {
                "ok": False,
                "error": "invalid_code",
                "message": error,
                "masked_email": user.email,
            },
            400,
        )
    request.session[PASSWORD_RESET_VERIFIED_SESSION_KEY] = True
    request.session.modified = True
    return (
        {
            "ok": True,
            "redirect": "/app/password-reset/set",
            "message": "確認コードが正しいことを確認しました。",
        },
        200,
    )


def password_reset_resend(request: HttpRequest) -> tuple[dict, int]:
    user = _password_reset_user(request)
    if not user:
        return (
            {
                "ok": False,
                "error": "no_pending",
                "redirect": "/app/password-reset",
                "message": "パスワード再設定はメールアドレスの入力からやり直してください。",
            },
            400,
        )
    try:
        create_and_send_password_reset_otp(user)
        request.session.pop(PASSWORD_RESET_VERIFIED_SESSION_KEY, None)
        request.session.modified = True
    except EmailConfigurationError as exc:
        return ({"ok": False, "error": "email_config", "message": str(exc)}, 503)
    except Exception:
        return (
            {
                "ok": False,
                "error": "email_send_failed",
                "message": "確認メールの送信に失敗しました。",
            },
            500,
        )
    return (
        {
            "ok": True,
            "message": "確認コードを再送信しました。",
            "masked_email": user.email,
        },
        200,
    )


def password_reset_set(request: HttpRequest, data: dict) -> tuple[dict, int]:
    user = _password_reset_user(request)
    if not user or not request.session.get(PASSWORD_RESET_VERIFIED_SESSION_KEY):
        return (
            {
                "ok": False,
                "error": "not_verified",
                "message": "確認コードの入力からやり直してください。",
                "redirect": "/app/password-reset/verify"
                if user
                else "/app/password-reset",
            },
            400,
        )
    form = PasswordResetSetForm(
        {
            "password1": data.get("password1") or "",
            "password2": data.get("password2") or "",
        }
    )
    if not form.is_valid():
        return (
            {
                "ok": False,
                "error": "validation",
                "errors": form_field_errors(form),
            },
            400,
        )
    user.set_password(form.cleaned_data["password1"])
    user.save(update_fields=["password"])
    clear_password_reset_session(request)
    return (
        {
            "ok": True,
            "redirect": "/app/login",
            "message": "パスワードを再設定しました。新しいパスワードでログインしてください。",
        },
        200,
    )


def verify_status(request: HttpRequest) -> dict[str, Any]:
    user = _pending_signup_user(request)
    return {
        "ok": True,
        "pending": bool(user),
        "masked_email": user.email if user else "",
    }


def password_reset_status(request: HttpRequest) -> dict[str, Any]:
    user = _password_reset_user(request)
    return {
        "ok": True,
        "pending": bool(user),
        "verified": bool(request.session.get(PASSWORD_RESET_VERIFIED_SESSION_KEY)),
        "masked_email": user.email if user else "",
    }
