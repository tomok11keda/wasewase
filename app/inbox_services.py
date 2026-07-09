"""DM インボックスとグループチャット一覧の統合表示。"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser

from .dm_services import build_dm_conversations, build_dm_unread_summary
from .group_chat_services import build_group_conversations, build_group_unread_summary


def build_inbox_conversations(user: AbstractBaseUser) -> list[dict]:
    items: list[dict] = []

    for dm in build_dm_conversations(user):
        partner = dm["partner"]
        if not partner:
            continue
        latest = dm["latest_message"]
        items.append(
            {
                "kind": "dm",
                "room": dm["room"],
                "partner": partner,
                "display_name": user_display_name_safe(partner),
                "subtitle": f"@{partner.username}",
                "latest_message": latest,
                "unread_count": dm["unread_count"],
                "updated_at": latest.created_at if latest else dm["room"].updated_at,
            }
        )

    for group in build_group_conversations(user):
        latest = group["latest_message"]
        member_count = group["member_count"]
        items.append(
            {
                "kind": "group",
                "room": group["room"],
                "partner": None,
                "display_name": group["display_name"],
                "subtitle": f"{member_count}人のグループ",
                "latest_message": latest,
                "unread_count": group["unread_count"],
                "updated_at": group["updated_at"],
            }
        )

    items.sort(key=lambda item: item["updated_at"], reverse=True)
    return items


def build_inbox_unread_summary(user: AbstractBaseUser) -> dict:
    dm_summary = build_dm_unread_summary(user)
    group_summary = build_group_unread_summary(user)
    rooms = [
        {"kind": "dm", "room_pk": room["room_pk"], "unread_count": room["unread_count"]}
        for room in dm_summary["rooms"]
    ] + list(group_summary["rooms"])
    return {
        "total_unread": dm_summary["total_unread"] + group_summary["total_unread"],
        "rooms": rooms,
    }


def user_display_name_safe(user) -> str:
    from .services import user_display_name

    return user_display_name(user)
