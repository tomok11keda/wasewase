"""個人・団体プロフィールの複数外部リンク。"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction

from .models import Organization, ProfileLink

PROFILE_LINK_MAX = 5
PROFILE_LINK_TITLE_MAX = 40
PROFILE_LINK_URL_MAX = 200
LEGACY_INSTAGRAM_TITLE = "Instagram"
LEGACY_WEBSITE_TITLE = "公式Webサイト"

_URL_VALIDATOR = URLValidator(schemes=("http", "https"))
LEGACY_URL_UNSET = object()


class ProfileLinkError(Exception):
    def __init__(self, error: str, status: int = 400, **extra: Any):
        self.error = error
        self.status = status
        self.extra = extra
        super().__init__(error)


def serialize_profile_link(link: ProfileLink) -> dict[str, Any]:
    return {
        "id": link.pk,
        "title": link.title or "",
        "url": link.url,
        "position": int(link.position),
    }


def serialize_user_links(user: AbstractBaseUser) -> list[dict[str, Any]]:
    links = getattr(user, "_prefetched_objects_cache", {}).get("profile_links")
    if links is None:
        links = list(user.profile_links.all())
    else:
        links = list(links)
    links.sort(key=lambda item: (item.position, item.pk))
    return [serialize_profile_link(link) for link in links]


def serialize_organization_links(organization: Organization) -> list[dict[str, Any]]:
    """ProfileLink を正本にする。行があるときは旧列を合成しない。

    行が 0 件のときだけ Instagram/Webサイト列を返す。0075 未適用や
    ORM で列だけ入った団体がチップから消えないようにする。
    新UIで削除したリンクは列も空になるため、ここでは復活しない。
    """
    links = getattr(organization, "_prefetched_objects_cache", {}).get("profile_links")
    if links is None:
        links = list(organization.profile_links.all())
    else:
        links = list(links)
    links.sort(key=lambda item: (item.position, item.pk))
    if links:
        return [serialize_profile_link(link) for link in links]
    return _serialized_legacy_column_links(organization)


def _serialized_legacy_column_links(organization: Organization) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for title, raw_url in (
        (LEGACY_INSTAGRAM_TITLE, organization.instagram_url or ""),
        (LEGACY_WEBSITE_TITLE, organization.website_url or ""),
    ):
        url = str(raw_url).strip()
        if not url:
            continue
        key = _normalize_url_key(url)
        if not key or key in seen:
            continue
        items.append(
            {
                "id": None,
                "title": title,
                "url": url,
                "position": len(items),
            }
        )
        seen.add(key)
    return items[:PROFILE_LINK_MAX]


def replace_user_profile_links(user: AbstractBaseUser, raw_items: Any) -> list[ProfileLink]:
    return _replace_links(user=user, organization=None, raw_items=raw_items)


def replace_organization_profile_links(
    organization: Organization, raw_items: Any
) -> list[ProfileLink]:
    created = _replace_links(user=None, organization=organization, raw_items=raw_items)
    _sync_organization_legacy_urls(organization, created)
    return created


def apply_legacy_organization_urls(
    organization: Organization,
    *,
    instagram_url: Any = LEGACY_URL_UNSET,
    website_url: Any = LEGACY_URL_UNSET,
    previous_instagram: str = "",
    previous_website: str = "",
) -> list[ProfileLink]:
    """旧 instagram_url / website_url だけが来たときの ProfileLink 整合。

    該当スロットだけ upsert/delete し、他の ProfileLink は消さない。
    追加で 5 件を超える場合は 400。同じ URL の二重登録はしない。
    """
    with transaction.atomic():
        if instagram_url is not LEGACY_URL_UNSET:
            _apply_legacy_slot(
                organization,
                new_url=str(instagram_url or "").strip(),
                previous_url=str(previous_instagram or "").strip(),
                field_name="instagram_url",
                title=LEGACY_INSTAGRAM_TITLE,
                insert_index=0,
                match_without_previous=_is_instagram_slot,
            )
        if website_url is not LEGACY_URL_UNSET:
            rows = _org_link_rows(organization)
            _apply_legacy_slot(
                organization,
                new_url=str(website_url or "").strip(),
                previous_url=str(previous_website or "").strip(),
                field_name="website_url",
                title=LEGACY_WEBSITE_TITLE,
                insert_index=_website_insert_index(rows),
                match_without_previous=_is_website_slot,
            )
        rows = _org_link_rows(organization)
        _sync_organization_legacy_urls(organization, rows)
        return rows


def sync_organization_legacy_columns(organization: Organization) -> None:
    rows = _org_link_rows(organization)
    _sync_organization_legacy_urls(organization, rows)


def _replace_links(
    *,
    user: AbstractBaseUser | None,
    organization: Organization | None,
    raw_items: Any,
) -> list[ProfileLink]:
    if bool(user) == bool(organization):
        raise ValueError("ProfileLink は user か organization のどちらか一方が必要です。")
    parsed = validate_link_items(raw_items)
    filters = {"user": user} if user is not None else {"organization": organization}
    rows = [
        ProfileLink(
            user=user,
            organization=organization,
            title=title,
            url=url,
            position=index,
        )
        for index, (title, url) in enumerate(parsed)
    ]
    with transaction.atomic():
        ProfileLink.objects.filter(**filters).delete()
        if rows:
            ProfileLink.objects.bulk_create(rows)
    return rows


def validate_link_items(raw_items: Any) -> list[tuple[str, str]]:
    if raw_items is None:
        items: list[Any] = []
    elif isinstance(raw_items, list):
        items = raw_items
    else:
        raise ProfileLinkError(
            "validation",
            errors={"links": ["リンクの形式が正しくありません。"]},
        )
    if len(items) > PROFILE_LINK_MAX:
        raise ProfileLinkError(
            "validation",
            errors={"links": [f"リンクは{PROFILE_LINK_MAX}件までです。"]},
        )

    parsed: list[tuple[str, str]] = []
    seen: set[str] = set()
    errors: dict[str, list[str]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.setdefault("links", []).append("リンクの形式が正しくありません。")
            continue
        title, title_errors = _clean_title(item.get("title"))
        url, url_errors = _clean_required_url(item.get("url"))
        if title_errors:
            errors[f"links.{index}.title"] = title_errors
        if url_errors:
            errors[f"links.{index}.url"] = url_errors
            continue
        key = _normalize_url_key(url)
        if key in seen:
            errors.setdefault("links", []).append("同じURLは登録できません。")
            continue
        seen.add(key)
        parsed.append((title, url))

    if errors:
        raise ProfileLinkError("validation", errors=errors)
    return parsed


def coerce_links_field(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            raise ProfileLinkError(
                "validation",
                errors={"links": ["リンクの形式が正しくありません。"]},
            ) from None
    return value


def _clean_title(value: Any) -> tuple[str, list[str]]:
    if value is None:
        return "", []
    if isinstance(value, (list, dict, bool)):
        return "", ["表示名の形式が正しくありません。"]
    title = str(value).strip()
    if len(title) > PROFILE_LINK_TITLE_MAX:
        return "", [f"表示名は{PROFILE_LINK_TITLE_MAX}文字以内で入力してください。"]
    return title, []


def _clean_required_url(value: Any) -> tuple[str, list[str]]:
    if value is None or isinstance(value, (list, dict, bool)):
        return "", ["URLを入力してください。"]
    url = str(value).strip()
    if not url:
        return "", ["URLを入力してください。"]
    if len(url) > PROFILE_LINK_URL_MAX:
        return "", [f"URLは{PROFILE_LINK_URL_MAX}文字以内で入力してください。"]
    scheme = urlsplit(url).scheme.lower()
    if scheme not in {"http", "https"}:
        return "", ["URLは http または https で始めてください。"]
    try:
        _URL_VALIDATOR(url)
    except ValidationError:
        return "", ["URLの形式が正しくありません。"]
    return url, []


def _normalize_url_key(url: str) -> str:
    try:
        parts = urlsplit(str(url).strip())
    except ValueError:
        return str(url).strip().rstrip("/").lower()
    scheme = (parts.scheme or "").lower()
    netloc = (parts.netloc or "").lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def is_instagram_url(url: str) -> bool:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return host == "instagram.com" or host.endswith(".instagram.com")


def _is_instagram_slot(link: ProfileLink) -> bool:
    title = (link.title or "").strip()
    return title == LEGACY_INSTAGRAM_TITLE or is_instagram_url(link.url)


def _is_website_slot(link: ProfileLink) -> bool:
    return (link.title or "").strip() == LEGACY_WEBSITE_TITLE


def _org_link_rows(organization: Organization) -> list[ProfileLink]:
    cache = getattr(organization, "_prefetched_objects_cache", None)
    if isinstance(cache, dict):
        cache.pop("profile_links", None)
    return list(organization.profile_links.order_by("position", "pk"))


def _website_insert_index(rows: list[ProfileLink]) -> int:
    last_ig = -1
    for index, link in enumerate(rows):
        if _is_instagram_slot(link):
            last_ig = index
    return last_ig + 1 if last_ig >= 0 else len(rows)


def _find_legacy_slot(
    rows: list[ProfileLink],
    previous_url: str,
    match_without_previous,
) -> ProfileLink | None:
    if previous_url:
        key = _normalize_url_key(previous_url)
        for link in rows:
            if _normalize_url_key(link.url) == key:
                return link
        return None
    for link in rows:
        if match_without_previous(link):
            return link
    return None


def _apply_legacy_slot(
    organization: Organization,
    *,
    new_url: str,
    previous_url: str,
    field_name: str,
    title: str,
    insert_index: int,
    match_without_previous,
) -> None:
    rows = _org_link_rows(organization)
    match = _find_legacy_slot(rows, previous_url, match_without_previous)
    if not new_url:
        if match is not None:
            _delete_link_and_resequence(organization, match)
        return

    new_key = _normalize_url_key(new_url)
    existing_same = next(
        (row for row in rows if _normalize_url_key(row.url) == new_key),
        None,
    )
    if match is not None:
        if existing_same is not None and existing_same.pk != match.pk:
            raise ProfileLinkError(
                "validation",
                errors={field_name: ["同じURLは登録できません。"]},
            )
        if match.url != new_url:
            match.url = new_url
            match.save(update_fields=["url", "updated_at"])
        return
    if existing_same is not None:
        return
    if len(rows) >= PROFILE_LINK_MAX:
        raise ProfileLinkError(
            "validation",
            errors={
                field_name: [
                    f"リンクは{PROFILE_LINK_MAX}件までです。これ以上追加できません。"
                ]
            },
        )
    _insert_organization_link(
        organization,
        title=title,
        url=new_url,
        index=insert_index,
        rows=rows,
    )


def _insert_organization_link(
    organization: Organization,
    *,
    title: str,
    url: str,
    index: int,
    rows: list[ProfileLink],
) -> None:
    index = max(0, min(index, len(rows)))
    for row in reversed(rows[index:]):
        ProfileLink.objects.filter(pk=row.pk).update(position=row.position + 1)
    ProfileLink.objects.create(
        organization=organization,
        title=title,
        url=url,
        position=index,
    )


def _delete_link_and_resequence(organization: Organization, link: ProfileLink) -> None:
    link.delete()
    rows = _org_link_rows(organization)
    for index, row in enumerate(rows):
        if row.position != 1000 + index:
            ProfileLink.objects.filter(pk=row.pk).update(position=1000 + index)
    for index, row in enumerate(rows):
        ProfileLink.objects.filter(pk=row.pk).update(position=index)


def copy_legacy_profile_urls_for_organization(organization: Organization) -> int:
    """列にある Instagram/Webサイト URL が未登録なら末尾に追加する。"""
    rows = _org_link_rows(organization)
    seen = {_copy_url_key(row.url) for row in rows}
    position = len(rows)
    created = 0
    for title, raw_url in (
        (LEGACY_INSTAGRAM_TITLE, organization.instagram_url or ""),
        (LEGACY_WEBSITE_TITLE, organization.website_url or ""),
    ):
        url = str(raw_url).strip()
        if not url:
            continue
        key = _copy_url_key(url)
        if not key or key in seen:
            continue
        if position >= PROFILE_LINK_MAX:
            break
        ProfileLink.objects.create(
            organization=organization,
            title=title,
            url=url,
            position=position,
        )
        seen.add(key)
        position += 1
        created += 1
    return created


def copy_organization_legacy_profile_urls(apps, schema_editor=None) -> None:
    """既存団体の Instagram / Webサイト列を ProfileLink に複製する。列は残す。

    現行コード用。0075 の RunPython は migration 内に同じロジックを固定している。
    """
    Organization = apps.get_model("app", "Organization")
    ProfileLink = apps.get_model("app", "ProfileLink")

    urls_by_org: dict[int, set[str]] = {}
    counts: dict[int, int] = {}
    for org_id, url in ProfileLink.objects.exclude(organization_id=None).values_list(
        "organization_id", "url"
    ):
        urls_by_org.setdefault(org_id, set()).add(_copy_url_key(url))
        counts[org_id] = counts.get(org_id, 0) + 1

    to_create = []
    orgs = Organization.objects.exclude(instagram_url="", website_url="").only(
        "id", "instagram_url", "website_url"
    )
    for org in orgs.iterator():
        seen = urls_by_org.setdefault(org.pk, set())
        position = counts.get(org.pk, 0)
        for title, raw_url in (
            (LEGACY_INSTAGRAM_TITLE, org.instagram_url or ""),
            (LEGACY_WEBSITE_TITLE, org.website_url or ""),
        ):
            url = str(raw_url).strip()
            if not url:
                continue
            key = _copy_url_key(url)
            if not key or key in seen:
                continue
            if position >= PROFILE_LINK_MAX:
                break
            to_create.append(
                ProfileLink(
                    organization_id=org.pk,
                    title=title,
                    url=url,
                    position=position,
                )
            )
            seen.add(key)
            position += 1
            counts[org.pk] = position
    if to_create:
        ProfileLink.objects.bulk_create(to_create)


def _copy_url_key(url: str) -> str:
    return str(url or "").strip().rstrip("/").lower()


def _sync_organization_legacy_urls(
    organization: Organization, links: list[ProfileLink]
) -> None:
    instagram = ""
    website = ""
    for link in links:
        url = (link.url or "").strip()
        if not url:
            continue
        if not instagram and is_instagram_url(url):
            instagram = url
            continue
        if not website:
            website = url
    updates: list[str] = []
    if organization.instagram_url != instagram:
        organization.instagram_url = instagram
        updates.append("instagram_url")
    if organization.website_url != website:
        organization.website_url = website
        updates.append("website_url")
    if updates:
        organization.save(update_fields=[*updates, "updated_at"])
