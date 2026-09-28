"""SPA timetable chrome: weekday grid plus an independent on-demand column."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class TimetableOnDemandColumnTests(SimpleTestCase):
    def test_spa_uses_independent_ondemand_column(self):
        page = _read("frontend/src/pages/TimetablePage.tsx")
        self.assertIn("timetable-od-panel", page)
        self.assertIn("listFilledOnDemandSlots", page)
        self.assertIn("nextFreeOnDemandSlotKey", page)
        self.assertIn("オンデマンドを追加", page)
        self.assertNotIn("TIMETABLE_OD_SLOTS.map", page)
        self.assertNotIn('kind="od"', page.split("function PeriodRow")[-1][:400])

    def test_spa_keeps_weekday_periods_and_slot_plumbing(self):
        page = _read("frontend/src/pages/TimetablePage.tsx")
        api = _read("frontend/src/features/timetable/api.ts")
        self.assertIn("TIMETABLE_DAYS", page)
        self.assertIn("TIMETABLE_PERIODS", page)
        self.assertIn("openOnDemandComposer", page)
        self.assertIn("saveSlot", page)
        self.assertIn("analytics.timetableViewed", page)
        self.assertIn("analytics.timetableSlotSaved", page)
        self.assertIn("listOnDemandSlotKeys", api)
        self.assertIn("od${od.number}-d${dayIndex}", api)
        self.assertIn('parsed.kind !== "od"', api)

    def test_empty_state_cta_and_quiet_plus_affordances(self):
        page = _read("frontend/src/pages/TimetablePage.tsx")
        css = _read("frontend/src/styles/timetable.css")
        self.assertIn("秋学期の時間割をつくろう", page)
        self.assertIn("授業を追加すると、あなたの1週間がここに表示されます", page)
        self.assertIn("data-timetable-empty-cta", page)
        self.assertIn("hasAnyCourse", page)
        self.assertIn("showEmptyCta", page)
        self.assertIn("＋ オンデマンドを追加", page)
        self.assertIn("timetable-empty-cta", css)
        self.assertIn("has-more::after", css)
        self.assertIn("-webkit-line-clamp: 2", css)
        self.assertIn(
            ".timetable-grid .timetable-slot.is-empty .timetable-slot__placeholder",
            css,
        )

    def test_ondemand_column_styles_do_not_use_extra_period_rows(self):
        css = _read("frontend/src/styles/timetable.css")
        self.assertIn(".timetable-layout", css)
        self.assertIn(".timetable-od-panel", css)
        self.assertIn("--tt-od-min", css)
        self.assertNotIn("repeat(2, minmax(48px, 0.92fr))", css)
