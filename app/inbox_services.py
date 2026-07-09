"""DM インボックスとグループチャット一覧の統合表示。"""

from __future__ import annotations

import logging

from django.contrib.auth.models import AbstractBaseUser

from .dm_services import build_dm_conversations, build_dm_unread_summary
from .group_chat_services import build_group_conversations, build_group_unread_summary

logger = logging.getLogger(__name__)


def build_inbox_conversations(user: AbstractBaseUser) -> list[dict]:
    items: list[dict] = []

    try:
        dm_conversations = build_dm_conversations(user)
    except Exception as exc:
        logger.warning("build_dm_conversations failed: %s", exc)
        dm_conversations = []

    for dm in dm_conversations:
        try:
            partner = dm.get("partner")
            if not partner:
                continue
            latest = dm.get("latest_message")
            room = dm.get("room")
            if room is None:
                continue
            username = (getattr(partner, "username", "") or "").strip()
            subtitle = f"@{username}" if username else "@(不明ユーザー)"
            items.append(
                {
                    "kind": "dm",
                    "room": room,
                    "partner": partner,
                    "display_name": user_display_name_safe(partner),
                    "subtitle": subtitle,
                    "latest_message": latest,
                    "latest_sender_display_name": user_display_name_safe(
                        getattr(latest, "sender", None)
                    )
                    if latest
                    else "",
                    "unread_count": int(dm.get("unread_count") or 0),
                    "updated_at": latest.created_at if latest else room.updated_at,
                }
            )
        except Exception as exc:
            logger.warning("Skipping broken DM conversation: %s", exc)
            continue

    try:
        group_conversations = build_group_conversations(user)
    except Exception as exc:
        logger.warning("build_group_conversations failed: %s", exc)
        group_conversations = []

    for group in group_conversations:
        try:
            latest = group.get("latest_message")
            member_count = int(group.get("member_count") or 0)
            room = group.get("room")
            if room is None:
                continue
            items.append(
                {
                    "kind": "group",
                    "room": room,
                    "partner": None,
                    "display_name": group.get("display_name")
                    or f"グループ #{getattr(room, 'pk', '')}",
                    "subtitle": f"{member_count}人のグループ",
                    "latest_message": latest,
                    "latest_sender_display_name": user_display_name_safe(
                        getattr(latest, "sender", None)
                    )
                    if latest
                    else "",
                    "unread_count": int(group.get("unread_count") or 0),
                    "updated_at": group.get("updated_at") or room.updated_at,
                }
            )
        except Exception as exc:
            logger.warning("Skipping broken group conversation: %s", exc)
            continue

    items.sort(key=lambda item: item["updated_at"], reverse=True)
    return items


def build_inbox_unread_summary(user: AbstractBaseUser) -> dict:
    try:
        dm_summary = build_dm_unread_summary(user)
    except Exception as exc:
        logger.warning("build_dm_unread_summary failed: %s", exc)
        dm_summary = {"total_unread": 0, "rooms": []}
    try:
        group_summary = build_group_unread_summary(user)
    except Exception as exc:
        logger.warning("build_group_unread_summary failed: %s", exc)
        group_summary = {"total_unread": 0, "rooms": []}
    rooms = [
        {"kind": "dm", "room_pk": room["room_pk"], "unread_count": room["unread_count"]}
        for room in dm_summary["rooms"]
    ] + list(group_summary["rooms"])
    return {
        "total_unread": dm_summary["total_unread"] + group_summary["total_unread"],
        "rooms": rooms,
    }


def get_unread_inbox_message_count(user: AbstractBaseUser | None) -> int:
    """ログインユーザー宛の未読メッセージ総数（1対1 DM + グループ）。"""
    if user is None or not getattr(user, "is_authenticated", False):
        return 0
    return build_inbox_unread_summary(user)["total_unread"]


def user_display_name_safe(user) -> str:
    from .services import user_display_name

    return user_display_name(user)
