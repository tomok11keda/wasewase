"""時間割表示・永続化用の定数・グリッド組み立て。"""

from __future__ import annotations

import re

from django.contrib.auth.models import AbstractBaseUser

from .models import TimetableSlot

TIMETABLE_DAYS = ("月", "火", "水", "木", "金", "土")

TIMETABLE_PERIODS = (
    {"number": 1, "label": "1限", "time": "8:50-10:30"},
    {"number": 2, "label": "2限", "time": "10:40-12:20"},
    {"number": 3, "label": "3限", "time": "13:10-14:50"},
    {"number": 4, "label": "4限", "time": "15:05-16:45"},
    {"number": 5, "label": "5限", "time": "17:00-18:40"},
)

TIMETABLE_OD_SLOTS = (
    {"number": 1, "label": "OD1", "time": "オンデマンド"},
    {"number": 2, "label": "OD2", "time": "オンデマンド"},
)

_SLOT_KEY_RE = re.compile(r"^(p|od)(\d+)-d(\d+)$")


def parse_slot_key(slot_key: str) -> dict | None:
    """slot_key → {kind, number, day_index}。不正なら None。"""
    raw = (slot_key or "").strip()
    match = _SLOT_KEY_RE.fullmatch(raw)
    if not match:
        return None
    prefix, number_s, day_s = match.groups()
    number = int(number_s)
    day_index = int(day_s)
    if day_index < 0 or day_index >= len(TIMETABLE_DAYS):
        return None
    if prefix == "p":
        if number < 1 or number > len(TIMETABLE_PERIODS):
            return None
        return {"kind": "period", "number": number, "day_index": day_index, "slot_key": raw}
    if number < 1 or number > len(TIMETABLE_OD_SLOTS):
        return None
    return {"kind": "od", "number": number, "day_index": day_index, "slot_key": raw}


def _normalize_cell(raw, *, slot_key, kind):
    raw = raw or {}
    return {
        "slot_key": slot_key,
        "kind": kind,
        "name": (raw.get("name") or "").strip(),
        "room": (raw.get("room") or "").strip(),
        "credits": (raw.get("credits") or "").strip(),
        "memo": (raw.get("memo") or "").strip(),
    }


def build_timetable_grid(entries=None, od_entries=None):
    """
    entries: {(period_number 1-5, day_index 0-5): {name, room, credits, memo}}
    od_entries: {(od_number 1-2, day_index 0-5): {name, room, credits, memo}}
    """
    lookup = entries or {}
    od_lookup = od_entries or {}
    rows = []
    for period in TIMETABLE_PERIODS:
        cells = []
        for day_index, day_label in enumerate(TIMETABLE_DAYS):
            slot_key = f"p{period['number']}-d{day_index}"
            cell = _normalize_cell(
                lookup.get((period["number"], day_index)),
                slot_key=slot_key,
                kind="period",
            )
            cell["day_label"] = day_label
            cell["day_index"] = day_index
            cells.append(cell)
        rows.append({"period": period, "cells": cells, "kind": "period"})

    od_rows = []
    for od_slot in TIMETABLE_OD_SLOTS:
        cells = []
        for day_index, day_label in enumerate(TIMETABLE_DAYS):
            slot_key = f"od{od_slot['number']}-d{day_index}"
            cell = _normalize_cell(
                od_lookup.get((od_slot["number"], day_index)),
                slot_key=slot_key,
                kind="od",
            )
            cell["day_label"] = day_label
            cell["day_index"] = day_index
            cells.append(cell)
        od_rows.append({"period": od_slot, "cells": cells, "kind": "od"})

    return {
        "days": TIMETABLE_DAYS,
        "rows": rows,
        "od_rows": od_rows,
        "day_count": len(TIMETABLE_DAYS),
    }


def slot_to_payload(slot: TimetableSlot) -> dict:
    return {
        "slot_key": slot.slot_key,
        "name": slot.name or "",
        "room": slot.room or "",
        "credits": slot.credits or "",
        "memo": slot.memo or "",
    }


def load_slot_maps_for_user(user: AbstractBaseUser | None) -> tuple[dict, dict]:
    """DB から (period_entries, od_entries) を組み立てる。"""
    entries: dict = {}
    od_entries: dict = {}
    if user is None or not getattr(user, "pk", None):
        return entries, od_entries

    for slot in TimetableSlot.objects.filter(user_id=user.pk).only(
        "slot_key", "name", "room", "credits", "memo"
    ):
        parsed = parse_slot_key(slot.slot_key)
        if parsed is None:
            continue
        payload = {
            "name": slot.name,
            "room": slot.room,
            "credits": slot.credits,
            "memo": slot.memo,
        }
        key = (parsed["number"], parsed["day_index"])
        if parsed["kind"] == "period":
            entries[key] = payload
        else:
            od_entries[key] = payload
    return entries, od_entries


def build_timetable_grid_for_user(user: AbstractBaseUser | None):
    entries, od_entries = load_slot_maps_for_user(user)
    return build_timetable_grid(entries, od_entries)


def slots_dict_for_user(user: AbstractBaseUser | None) -> dict[str, dict]:
    if user is None or not getattr(user, "pk", None):
        return {}
    return {
        slot.slot_key: slot_to_payload(slot)
        for slot in TimetableSlot.objects.filter(user_id=user.pk)
    }


def upsert_timetable_slot(
    user: AbstractBaseUser,
    *,
    slot_key: str,
    name: str = "",
    room: str = "",
    credits: str = "",
    memo: str = "",
) -> TimetableSlot | None:
    """空内容なら削除して None。それ以外は upsert。不正キーは ValueError。"""
    parsed = parse_slot_key(slot_key)
    if parsed is None:
        raise ValueError("invalid slot_key")

    name = (name or "").strip()
    room = (room or "").strip()
    credits = (credits or "").strip()
    memo = (memo or "").strip()
    if parsed["kind"] == "od":
        room = ""

    if not name and not room and not credits and not memo:
        TimetableSlot.objects.filter(user=user, slot_key=parsed["slot_key"]).delete()
        return None

    slot, _created = TimetableSlot.objects.update_or_create(
        user=user,
        slot_key=parsed["slot_key"],
        defaults={
            "name": name,
            "room": room,
            "credits": credits,
            "memo": memo,
        },
    )
    return slot
