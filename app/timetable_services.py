"""時間割表示用の定数・グリッド組み立て。"""

TIMETABLE_DAYS = ("月", "火", "水", "木", "金")

TIMETABLE_PERIODS = (
    {"number": 1, "label": "1限", "time": "8:50-10:30"},
    {"number": 2, "label": "2限", "time": "10:40-12:20"},
    {"number": 3, "label": "3限", "time": "13:10-14:50"},
    {"number": 4, "label": "4限", "time": "15:05-16:45"},
    {"number": 5, "label": "5限", "time": "17:00-18:40"},
)


def build_timetable_grid(entries=None):
    """
    entries: {(period_number 1-5, day_index 0-4): {"name": str, "room": str}}
    戻り値: periods × days のセル行列（未設定は None）。
    """
    lookup = entries or {}
    rows = []
    for period in TIMETABLE_PERIODS:
        cells = []
        for day_index, _day in enumerate(TIMETABLE_DAYS):
            cell = lookup.get((period["number"], day_index))
            if cell:
                cells.append(
                    {
                        "name": (cell.get("name") or "").strip(),
                        "room": (cell.get("room") or "").strip(),
                    }
                )
            else:
                cells.append(None)
        rows.append({"period": period, "cells": cells})
    return {
        "days": TIMETABLE_DAYS,
        "rows": rows,
    }
