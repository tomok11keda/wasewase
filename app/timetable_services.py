"""時間割表示用の定数・グリッド組み立て。"""

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
