"""DM インボックスとグループ・取引チャット一覧の統合表示。"""

from __future__ import annotations

import logging

from django.contrib.auth.models import AbstractBaseUser

from .dm_services import build_dm_conversations, build_dm_unread_summary
from .group_chat_services import build_group_conversations, build_group_unread_summary
from .trade_chat_inbox_services import (
    build_trade_chat_conversations,
    build_trade_chat_unread_summary,
)
from .ugc_services import is_user_blocked

logger = logging.getLogger(__name__)

INBOX_TAB_ALL = "all"
INBOX_TAB_TRADE = "trade"
INBOX_TAB_DM = "dm"
INBOX_TABS = (INBOX_TAB_ALL, INBOX_TAB_TRADE, INBOX_TAB_DM)


def normalize_inbox_tab(raw: str | None) -> str:
    tab = (raw or "").strip().lower()
    if tab in INBOX_TABS:
        return tab
    return INBOX_TAB_ALL


def filter_inbox_by_tab(items: list[dict], tab: str) -> list[dict]:
    tab = normalize_inbox_tab(tab)
    if tab == INBOX_TAB_TRADE:
        return [item for item in items if item.get("kind") == "trade"]
    if tab == INBOX_TAB_DM:
        return [item for item in items if item.get("kind") in ("dm", "group")]
    return items


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
            partner_blocked = is_user_blocked(user, partner)
            if partner_blocked:
                display_name = "不明なユーザー"
                subtitle = "ブロック中"
                latest_sender_name = "不明なユーザー" if latest else ""
            else:
                display_name = user_display_name_safe(partner)
                subtitle = f"@{username}" if username else "@(不明ユーザー)"
                latest_sender_name = (
                    user_display_name_safe(getattr(latest, "sender", None))
                    if latest
                    else ""
                )
            items.append(
                {
                    "kind": "dm",
                    "room": room,
                    "partner": partner,
                    "display_name": display_name,
                    "subtitle": subtitle,
                    "latest_message": latest,
                    "latest_sender_display_name": latest_sender_name,
                    "is_blocked": partner_blocked,
                    "unread_count": int(dm.get("unread_count") or 0),
                    "updated_at": latest.created_at if latest else room.updated_at,
                    "thumbnail_url": "",
                    "status_label": "",
                    "product": None,
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
                    "thumbnail_url": "",
                    "status_label": "",
                    "product": None,
                }
            )
        except Exception as exc:
            logger.warning("Skipping broken group conversation: %s", exc)
            continue

    try:
        trade_conversations = build_trade_chat_conversations(user)
    except Exception as exc:
        logger.warning("build_trade_chat_conversations failed: %s", exc)
        trade_conversations = []

    for trade in trade_conversations:
        try:
            latest = trade.get("latest_message")
            partner = trade.get("partner")
            items.append(
                {
                    "kind": "trade",
                    "room": trade["room"],
                    "partner": partner,
                    "product": trade.get("product"),
                    "display_name": trade.get("display_name") or "取引チャット",
                    "subtitle": trade.get("subtitle") or "取引チャット",
                    "status_label": trade.get("status_label") or "",
                    "thumbnail_url": trade.get("thumbnail_url") or "",
                    "latest_message": latest,
                    "latest_sender_display_name": user_display_name_safe(
                        getattr(latest, "sender", None)
                    )
                    if latest
                    else "",
                    "unread_count": int(trade.get("unread_count") or 0),
                    "updated_at": trade.get("updated_at")
                    or trade["room"].updated_at,
                    "is_blocked": False,
                }
            )
        except Exception as exc:
            logger.warning("Skipping broken trade conversation: %s", exc)
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
    try:
        trade_summary = build_trade_chat_unread_summary(user)
    except Exception as exc:
        logger.warning("build_trade_chat_unread_summary failed: %s", exc)
        trade_summary = {"total_unread": 0, "rooms": []}

    rooms = (
        [
            {
                "kind": "dm",
                "room_pk": room["room_pk"],
                "unread_count": room["unread_count"],
            }
            for room in dm_summary["rooms"]
        ]
        + list(group_summary["rooms"])
        + list(trade_summary["rooms"])
    )
    return {
        "total_unread": (
            dm_summary["total_unread"]
            + group_summary["total_unread"]
            + trade_summary["total_unread"]
        ),
        "rooms": rooms,
    }


def get_unread_inbox_message_count(user: AbstractBaseUser | None) -> int:
    """ログインユーザー宛の未読メッセージ総数（1対1 DM + グループ + 取引）。"""
    if user is None or not getattr(user, "is_authenticated", False):
        return 0
    return build_inbox_unread_summary(user)["total_unread"]


def user_display_name_safe(user) -> str:
    from .services import user_display_name

    return user_display_name(user)
