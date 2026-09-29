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


class TimetableSectionTabVisibilityTests(SimpleTestCase):
    def test_section_tabs_are_own_surface_not_embedded_gated(self):
        page = _read("frontend/src/pages/TimetablePage.tsx")
        surface = _read("frontend/src/features/timetable/surface.ts")
        self.assertIn("{ id: \"calendar\", label: \"カレンダー\" }", page)
        self.assertIn("tt-section-tabs", page)
        self.assertIn("showSectionTabs = !viewingOther", page)
        self.assertNotIn("showSectionTabs = !embedded && !viewingOther", page)
        self.assertIn("resolveTimetableTargetUserPk", page)
        self.assertIn("isOwnTimetableSurface", page)
        self.assertIn("me?.user?.id", page)
        self.assertIn("ignoreRouteUserPk", page)
        self.assertIn("if (input.ignoreRouteUserPk) return undefined", surface)
        self.assertIn("if (!input.targetUserPk) return true", surface)
        self.assertIn("String(input.myUserId) === input.targetUserPk", surface)
        tabs_gate = page.split("const showSectionTabs")[1].split("const canAddCourses")[0]
        for needle in ("events", "loading", "courses", "semester", "fetchCalendar"):
            self.assertNotIn(needle, tabs_gate)

    def test_keep_alive_own_timetable_ignores_route_user_pk(self):
        keep = _read("frontend/src/layouts/TabKeepAliveLayout.tsx")
        app = _read("frontend/src/App.tsx")
        self.assertIn("<TimetablePage ignoreRouteUserPk />", keep)
        self.assertIn(
            'path="timetable/user/:userPk" element={<TimetablePage />}',
            app,
        )
        self.assertNotIn("ignoreRouteUserPk", app)

    def test_profile_embed_uses_override_and_own_other_identity(self):
        profile = _read("frontend/src/pages/ProfilePage.tsx")
        page = _read("frontend/src/pages/TimetablePage.tsx")
        self.assertIn(
            "<TimetablePage key={userPk} overrideUserPk={userPk} embedded />",
            profile,
        )
        self.assertNotIn("ignoreRouteUserPk", profile)
        self.assertIn("overrideUserPk", page)
        self.assertIn("embedded", page)

    def test_other_surfaces_do_not_mount_calendar_view(self):
        page = _read("frontend/src/pages/TimetablePage.tsx")
        self.assertIn("showSectionTabs && section === \"calendar\"", page)
        self.assertIn("TimetableCalendarView", page)
        calendar_branch = page.split("showSectionTabs && section === \"calendar\"")[1].split(
            "showEmptyCta"
        )[0]
        self.assertIn("<TimetableCalendarView", calendar_branch)

    def test_stale_other_fetch_cannot_overwrite_own_state(self):
        page = _read("frontend/src/pages/TimetablePage.tsx")
        self.assertIn("loadGenRef", page)
        self.assertIn("const isStale = () => gen !== loadGenRef.current", page)
        self.assertIn("if (isStale()) return", page)
        self.assertIn("loadGenRef.current += 1", page)
        self.assertIn("if (!isStale()) setLoading(false)", page)

