from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

from .constants import HANDLE_MENTION_PATTERN
from .models import Notification, User
from .services import user_display_name
from .ugc_services import get_blocked_user_ids, is_user_blocked


def extract_mention_usernames(text: str) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for match in HANDLE_MENTION_PATTERN.finditer(text):
        username = match.group(1)
        key = username.lower()
        if key not in seen:
            seen.add(key)
            result.append(username)
    return result


def _mention_recipient_map(usernames: list[str]) -> dict[str, User]:
    if not usernames:
        return {}
    recipients: dict[str, User] = {}
    for username in usernames:
        user = User.objects.filter(username__iexact=username).first()
        if user:
            recipients[username.lower()] = user
    return recipients


def notify_mentions(
    *,
    body: str,
    actor: AbstractBaseUser,
    link: str,
    exclude_user_ids: set[int] | None = None,
) -> None:
    usernames = extract_mention_usernames(body)
    if not usernames or not actor.is_authenticated:
        return

    exclude = set(exclude_user_ids or [])
    exclude.add(actor.pk)
    blocked_ids = get_blocked_user_ids(actor)
    actor_label = user_display_name(actor)

    for username in usernames:
        user = User.objects.filter(username__iexact=username).first()
        if not user or user.pk in exclude or user.pk in blocked_ids:
            continue
        if is_user_blocked(user, actor):
            continue
        Notification.objects.create(
            recipient=user,
            message=f"{actor_label}さんがあなたをメンションしました",
            link=link,
        )


def linkify_mentions(text: str) -> SafeString | str:
    if not text:
        return ""
    usernames = extract_mention_usernames(text)
    recipient_map = _mention_recipient_map(usernames)
    if not recipient_map:
        return escape(text)

    escaped = escape(text)

    def replace(match):
        username = match.group(1)
        user = recipient_map.get(username.lower())
        if not user:
            return match.group(0)
        url = reverse("user_profile", kwargs={"pk": user.pk})
        return f'<a href="{url}" class="mention-link">@{username}</a>'

    return mark_safe(HANDLE_MENTION_PATTERN.sub(replace, escaped))
