"""Own-profile JSON API. Reuses AccountProfileForm; no schema change."""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, QueryDict
from django.http.multipartparser import MultiPartParser, MultiPartParserError
from django.utils.datastructures import MultiValueDict

from .constants import FACULTY_CHOICES, GRADE_CHOICES
from .forms import AccountProfileForm
from .handle_services import public_username
from .models import UserProfile
from .profile_api_services import serialize_profile_user
from .timetable_privacy_services import get_or_create_profile

EDITABLE_FIELDS = frozenset(
    {"name", "bio", "avatar", "department", "grade", "user_id", "username", "links"}
)
_LINKS_UNSET = object()
FORBIDDEN_FIELDS = frozenset(
    {
        "id",
        "pk",
        "email",
        "password",
        "is_staff",
        "is_superuser",
        "is_private",
        "is_operator_verified",
        "onboarding_step",
        "onboarding_completed_at",
        "onboarding_exempt",
        "terms_accepted",
        "is_timetable_public",
    }
)
_MULTIPART_IGNORED_KEYS = frozenset({"csrfmiddlewaretoken"})


class MeProfileApiError(Exception):
    def __init__(self, error: str, status: int = 400, **extra: Any):
        self.error = error
        self.status = status
        self.extra = extra
        super().__init__(error)


def _choice_options(choices, *, include_blank: bool) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen_blank = False
    for value, label in choices:
        if value == "":
            seen_blank = True
        items.append({"value": str(value), "label": str(label)})
    if include_blank and not seen_blank:
        items.insert(0, {"value": "", "label": "未設定"})
    return items


def serialize_own_profile_payload(user: AbstractBaseUser) -> dict[str, Any]:
    from .profile_link_services import serialize_user_links

    profile = get_or_create_profile(user)
    user.refresh_from_db()
    payload_user = serialize_profile_user(user, profile)
    payload_user["name"] = getattr(profile, "name", None) or ""
    payload_user["username"] = public_username(user)
    payload_user["links"] = serialize_user_links(user)
    return {
        "ok": True,
        "profile": payload_user,
        "choices": {
            "department": _choice_options(FACULTY_CHOICES, include_blank=True),
            "grade": _choice_options(GRADE_CHOICES, include_blank=False),
        },
    }


def _instance_form_data(profile: UserProfile, user: AbstractBaseUser) -> dict[str, str]:
    return {
        "name": getattr(profile, "name", None) or "",
        "bio": getattr(profile, "bio", None) or "",
        "department": getattr(profile, "department", None) or "",
        "grade": getattr(profile, "grade", None) or "",
        "user_id": public_username(user) or "",
    }


def _stringify_form_errors(form: AccountProfileForm) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    for field, field_errors in form.errors.items():
        errors[field] = [str(message) for message in field_errors]
    return errors


def parse_own_profile_update_request(request: HttpRequest) -> dict[str, Any]:
    content_type = (request.content_type or "").lower()
    if request.FILES or "multipart/form-data" in content_type:
        return _parse_multipart_update(request)
    if "application/json" in content_type:
        return _parse_json_update(request)
    raise MeProfileApiError("unsupported_media_type")


def _parse_json_update(request: HttpRequest) -> dict[str, Any]:
    raw = request.body or b""
    if not raw.strip():
        data: Any = {}
    else:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            raise MeProfileApiError("invalid_json") from exc
    if not isinstance(data, dict):
        raise MeProfileApiError("invalid_json")
    _assert_allowed_keys(data.keys())
    if "avatar" in data:
        raise MeProfileApiError(
            "validation",
            errors={"avatar": ["画像は multipart/form-data で送信してください。"]},
        )
    return _normalize_patch_fields(
        {key: data[key] for key in data if key in EDITABLE_FIELDS}
    )


def _parse_multipart_update(request: HttpRequest) -> dict[str, Any]:
    post, files = _load_multipart(request)
    keys = set(post.keys()) | set(files.keys())
    _assert_allowed_keys(keys)
    fields: dict[str, Any] = {}
    for key in ("name", "bio", "department", "grade", "user_id", "username", "links"):
        if key in post:
            fields[key] = post.get(key)
    avatar = files.get("avatar")
    if avatar is not None:
        fields["avatar"] = avatar
    return _normalize_patch_fields(fields)


def _load_multipart(request: HttpRequest) -> tuple[QueryDict, MultiValueDict]:
    if request.method == "POST":
        return request.POST, request.FILES
    try:
        parser = MultiPartParser(
            request.META,
            BytesIO(request.body),
            list(request.upload_handlers),
            request.encoding,
        )
        return parser.parse()
    except MultiPartParserError as exc:
        raise MeProfileApiError("invalid_multipart") from exc


def _assert_allowed_keys(keys) -> None:
    present = []
    for key in keys:
        if key in _MULTIPART_IGNORED_KEYS:
            continue
        present.append(key)
    forbidden = sorted({key for key in present if key in FORBIDDEN_FIELDS})
    if forbidden:
        raise MeProfileApiError("forbidden_field", fields=forbidden)
    unknown = sorted(
        {
            key
            for key in present
            if key not in EDITABLE_FIELDS and key not in FORBIDDEN_FIELDS
        }
    )
    if unknown:
        raise MeProfileApiError("unknown_field", fields=unknown)


def _normalize_patch_fields(fields: dict[str, Any]) -> dict[str, Any]:
    from .profile_link_services import ProfileLinkError, coerce_links_field

    normalized = dict(fields)
    if "username" in normalized and "user_id" not in normalized:
        normalized["user_id"] = normalized.pop("username")
    elif "username" in normalized:
        normalized.pop("username")
    if "links" in normalized:
        try:
            normalized["links"] = coerce_links_field(normalized["links"])
        except ProfileLinkError as exc:
            raise MeProfileApiError(exc.error, status=exc.status, **exc.extra) from exc
    return normalized


def update_own_profile(user: AbstractBaseUser, fields: dict[str, Any]) -> dict[str, Any]:
    from .profile_link_services import ProfileLinkError, replace_user_profile_links

    links = fields.pop("links", _LINKS_UNSET)
    profile = get_or_create_profile(user)
    data = _instance_form_data(profile, user)
    files = None
    for key, value in fields.items():
        if key == "avatar":
            files = MultiValueDict({"avatar": [value]})
            continue
        if key not in data:
            continue
        if value is None:
            data[key] = ""
        else:
            data[key] = value
    form = AccountProfileForm(data, files, instance=profile, user=user)
    if not form.is_valid():
        raise MeProfileApiError("validation", errors=_stringify_form_errors(form))
    try:
        with transaction.atomic():
            form.save()
            if links is not _LINKS_UNSET:
                try:
                    replace_user_profile_links(user, links)
                except ProfileLinkError as exc:
                    raise MeProfileApiError(
                        exc.error, status=exc.status, **exc.extra
                    ) from exc
    except ValidationError as exc:
        messages = [str(message) for message in exc.messages]
        raise MeProfileApiError(
            "validation",
            errors={"user_id": messages or ["ユーザー情報の更新に失敗しました。"]},
        ) from exc
    user.refresh_from_db()
    return serialize_own_profile_payload(user)
