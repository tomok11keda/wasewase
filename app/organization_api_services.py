"""団体プロフィール JSON API（Phase 1-B）。公開情報の取得と管理者による通常編集。"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.http import HttpRequest, QueryDict
from django.http.multipartparser import MultiPartParser, MultiPartParserError
from django.utils.datastructures import MultiValueDict

from .media_services import validate_timeline_image_file
from .models import Organization, OrganizationMember
from .organization_services import (
    can_manage_organization,
    can_view_organization_profile,
    get_organization_membership_role,
)

_MANAGED_LIST_STATUSES = (
    Organization.Status.DRAFT,
    Organization.Status.ACTIVE,
)
_MANAGED_LIST_ROLES = (
    OrganizationMember.Role.OWNER,
    OrganizationMember.Role.ADMIN,
)
_MANAGED_LIST_FIELDS = (
    "id",
    "name",
    "slug",
    "avatar_url",
    "is_verified",
    "my_role",
    "can_manage",
)

DESCRIPTION_MAX_LENGTH = 5000
ORGANIZATION_NAME_MAX_LENGTH = Organization._meta.get_field("name").max_length
ORGANIZATION_URL_MAX_LENGTH = Organization._meta.get_field("website_url").max_length

EDITABLE_FIELDS = frozenset(
    {
        "name",
        "description",
        "avatar",
        "category",
        "instagram_url",
        "website_url",
    }
)
FORBIDDEN_FIELDS = frozenset(
    {
        "id",
        "pk",
        "slug",
        "status",
        "is_listed",
        "is_verified",
        "created_at",
        "updated_at",
        "memberships",
        "members",
        "member_ids",
        "role",
        "my_role",
        "can_manage",
        "user",
        "user_id",
        "user_ids",
        "email",
        "owner",
        "owners",
        "admin",
        "admins",
        "is_operator_verified",
    }
)
_MULTIPART_IGNORED_KEYS = frozenset({"csrfmiddlewaretoken"})
_URL_VALIDATOR = URLValidator(schemes=("http", "https"))


class OrganizationApiError(Exception):
    def __init__(self, error: str, status: int = 400, **extra: Any):
        self.error = error
        self.status = status
        self.extra = extra
        super().__init__(error)


def get_organization_by_slug(slug: str) -> Organization | None:
    raw = (slug or "").strip()
    if not raw:
        return None
    return Organization.objects.filter(slug__iexact=raw).first()


def get_organization_avatar_url(organization: Organization) -> str:
    avatar = getattr(organization, "avatar", None)
    if not avatar:
        return ""
    try:
        return avatar.url or ""
    except Exception:
        return ""


def serialize_managed_organization(
    organization: Organization,
    viewer: AbstractBaseUser | None,
) -> dict[str, Any]:
    return {
        "id": organization.pk,
        "name": organization.name,
        "slug": organization.slug,
        "avatar_url": get_organization_avatar_url(organization),
        "is_verified": bool(organization.is_verified),
        "my_role": get_organization_membership_role(viewer, organization),
        "can_manage": can_manage_organization(viewer, organization),
    }


def list_managed_organizations_payload(viewer: AbstractBaseUser | None) -> dict[str, Any]:
    if viewer is None or not getattr(viewer, "is_authenticated", False):
        raise OrganizationApiError(
            "unauthorized",
            status=401,
            message="authentication_required",
        )
    if not getattr(viewer, "pk", None):
        return {"ok": True, "organizations": []}

    queryset = (
        Organization.objects.filter(
            memberships__user_id=viewer.pk,
            memberships__role__in=_MANAGED_LIST_ROLES,
            status__in=_MANAGED_LIST_STATUSES,
        )
        .distinct()
        .order_by("name", "pk")
    )
    organizations = []
    for organization in queryset:
        if not can_manage_organization(viewer, organization):
            continue
        item = serialize_managed_organization(organization, viewer)
        organizations.append({key: item[key] for key in _MANAGED_LIST_FIELDS})
    return {"ok": True, "organizations": organizations}


def serialize_organization_profile(
    organization: Organization,
    viewer: AbstractBaseUser | None,
) -> dict[str, Any]:
    from .organization_recruiting_chat_services import serialize_recruiting_chat_summary

    return {
        "ok": True,
        "organization": {
            "id": organization.pk,
            "name": organization.name,
            "slug": organization.slug,
            "description": organization.description or "",
            "avatar_url": get_organization_avatar_url(organization),
            "category": organization.category,
            "instagram_url": organization.instagram_url or "",
            "website_url": organization.website_url or "",
            "is_verified": bool(organization.is_verified),
        },
        "can_manage": can_manage_organization(viewer, organization),
        "my_role": get_organization_membership_role(viewer, organization),
        "recruiting_chat": serialize_recruiting_chat_summary(organization, viewer),
    }


def build_organization_profile_payload(
    organization: Organization | None,
    viewer: AbstractBaseUser | None,
) -> dict[str, Any]:
    if organization is None or not can_view_organization_profile(viewer, organization):
        raise OrganizationApiError("not_found", status=404)
    return serialize_organization_profile(organization, viewer)


def update_organization_profile(
    organization: Organization,
    actor: AbstractBaseUser | None,
    fields: dict[str, Any],
) -> dict[str, Any]:
    if not can_view_organization_profile(actor, organization):
        raise OrganizationApiError("not_found", status=404)
    if not can_manage_organization(actor, organization):
        raise OrganizationApiError("forbidden", status=403)

    validated = _validate_update_fields(fields)
    if not validated:
        return serialize_organization_profile(organization, actor)

    with transaction.atomic():
        locked = Organization.objects.select_for_update().get(pk=organization.pk)
        if not can_manage_organization(actor, locked):
            raise OrganizationApiError("forbidden", status=403)
        for key, value in validated.items():
            setattr(locked, key, value)
        locked.save(update_fields=[*validated.keys(), "updated_at"])

    locked.refresh_from_db()
    return serialize_organization_profile(locked, actor)


def parse_organization_update_request(request: HttpRequest) -> dict[str, Any]:
    content_type = (request.content_type or "").lower()
    if request.FILES or "multipart/form-data" in content_type:
        return _parse_multipart_update(request)
    if "application/json" in content_type:
        return _parse_json_update(request)
    raise OrganizationApiError("unsupported_media_type")


def _parse_json_update(request: HttpRequest) -> dict[str, Any]:
    raw = request.body or b""
    if not raw.strip():
        data: Any = {}
    else:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            raise OrganizationApiError("invalid_json") from exc
    if not isinstance(data, dict):
        raise OrganizationApiError("invalid_json")
    _assert_no_forbidden_or_unknown_fields(data.keys())
    if "avatar" in data:
        raise OrganizationApiError(
            "validation",
            errors={"avatar": ["画像は multipart/form-data で送信してください。"]},
        )
    return {key: data[key] for key in data if key in EDITABLE_FIELDS}


def _parse_multipart_update(request: HttpRequest) -> dict[str, Any]:
    post, files = _load_multipart(request)
    keys = set(post.keys()) | set(files.keys())
    _assert_no_forbidden_or_unknown_fields(keys)
    fields: dict[str, Any] = {}
    for key in EDITABLE_FIELDS:
        if key == "avatar":
            continue
        if key in post:
            fields[key] = post.get(key)
    avatar = files.get("avatar")
    if avatar is not None:
        fields["avatar"] = avatar
    return fields


def _load_multipart(request: HttpRequest) -> tuple[QueryDict, MultiValueDict]:
    """PATCH でも既存の Django multipart パーサを使う。POST 専用の request.FILES には頼らない。"""
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
        raise OrganizationApiError("invalid_multipart") from exc


def _assert_no_forbidden_or_unknown_fields(keys) -> None:
    present = []
    for key in keys:
        if key in _MULTIPART_IGNORED_KEYS:
            continue
        present.append(key)
    forbidden = sorted({key for key in present if key in FORBIDDEN_FIELDS})
    if forbidden:
        raise OrganizationApiError("forbidden_field", fields=forbidden)
    unknown = sorted(
        {key for key in present if key not in EDITABLE_FIELDS and key not in FORBIDDEN_FIELDS}
    )
    if unknown:
        raise OrganizationApiError("unknown_field", fields=unknown)


def _validate_update_fields(fields: dict[str, Any]) -> dict[str, Any]:
    errors: dict[str, list[str]] = {}
    validated: dict[str, Any] = {}

    if "name" in fields:
        name, name_errors = _clean_required_text(
            fields["name"],
            label="団体名",
            max_length=ORGANIZATION_NAME_MAX_LENGTH,
        )
        if name_errors:
            errors["name"] = name_errors
        else:
            validated["name"] = name

    if "description" in fields:
        description, description_errors = _clean_optional_text(
            fields["description"],
            label="団体説明",
            max_length=DESCRIPTION_MAX_LENGTH,
        )
        if description_errors:
            errors["description"] = description_errors
        else:
            validated["description"] = description

    if "category" in fields:
        category, category_errors = _clean_category(fields["category"])
        if category_errors:
            errors["category"] = category_errors
        else:
            validated["category"] = category

    if "instagram_url" in fields:
        url, url_errors = _clean_optional_url(fields["instagram_url"], label="Instagram URL")
        if url_errors:
            errors["instagram_url"] = url_errors
        else:
            validated["instagram_url"] = url

    if "website_url" in fields:
        url, url_errors = _clean_optional_url(fields["website_url"], label="Webサイト URL")
        if url_errors:
            errors["website_url"] = url_errors
        else:
            validated["website_url"] = url

    if "avatar" in fields:
        avatar, avatar_errors = _clean_avatar(fields["avatar"])
        if avatar_errors:
            errors["avatar"] = avatar_errors
        else:
            validated["avatar"] = avatar

    if errors:
        raise OrganizationApiError("validation", errors=errors)
    return validated


def _clean_required_text(value: Any, *, label: str, max_length: int) -> tuple[str, list[str]]:
    if value is None or isinstance(value, (list, dict, bool)):
        return "", [f"{label}を入力してください。"]
    text = str(value).strip()
    if not text:
        return "", [f"{label}を入力してください。"]
    if len(text) > max_length:
        return "", [f"{label}は{max_length}文字以内で入力してください。"]
    return text, []


def _clean_optional_text(value: Any, *, label: str, max_length: int) -> tuple[str, list[str]]:
    if value is None:
        return "", []
    if isinstance(value, (list, dict, bool)):
        return "", [f"{label}の形式が正しくありません。"]
    text = str(value).strip()
    if len(text) > max_length:
        return "", [f"{label}は{max_length}文字以内で入力してください。"]
    return text, []


def _clean_category(value: Any) -> tuple[str, list[str]]:
    if value is None or isinstance(value, (list, dict, bool)):
        return "", ["カテゴリを選択してください。"]
    category = str(value).strip()
    allowed = {choice[0] for choice in Organization.Category.choices}
    if category not in allowed:
        return "", ["カテゴリを選択してください。"]
    return category, []


def _clean_optional_url(value: Any, *, label: str) -> tuple[str, list[str]]:
    if value is None:
        return "", []
    if isinstance(value, (list, dict, bool)):
        return "", [f"{label}の形式が正しくありません。"]
    url = str(value).strip()
    if not url:
        return "", []
    if len(url) > ORGANIZATION_URL_MAX_LENGTH:
        return "", [f"{label}は{ORGANIZATION_URL_MAX_LENGTH}文字以内で入力してください。"]
    try:
        _URL_VALIDATOR(url)
    except ValidationError:
        return "", [f"{label}の形式が正しくありません。"]
    return url, []


def _clean_avatar(value: Any) -> tuple[Any, list[str]]:
    if value is None or not getattr(value, "name", ""):
        return None, ["画像ファイルを選択してください。"]
    try:
        validate_timeline_image_file(value)
    except ValidationError as exc:
        return None, [str(message) for message in exc.messages]
    return value, []
