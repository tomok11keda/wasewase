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
        calendar_branch = page.split(
            ") : showSectionTabs && section === \"calendar\" ? ("
        )[1].split("showEmptyCta")[0]
        self.assertIn("<TimetableCalendarView", calendar_branch)

    def test_stale_other_fetch_cannot_overwrite_own_state(self):
        page = _read("frontend/src/pages/TimetablePage.tsx")
        self.assertIn("loadGenRef", page)
        self.assertIn("const isStale = () => gen !== loadGenRef.current", page)
        self.assertIn("if (isStale()) return", page)
        self.assertIn("loadGenRef.current += 1", page)
        self.assertIn("if (!isStale()) setLoading(false)", page)


class TimetableMobileRowHeightTests(SimpleTestCase):
    def test_period_rows_fill_remaining_viewport_without_changing_columns(self):
        css = _read("frontend/src/styles/timetable.css")
        api = _read("frontend/src/features/timetable/api.ts")
        self.assertIn("--tt-day-min: 54px", css)
        self.assertIn("--tt-period-w: 46px", css)
        self.assertIn("--tt-od-min: 108px", css)
        self.assertIn("--tt-period-rows: 5", css)
        self.assertIn("{ number: 5, label: \"5限\"", api)
        self.assertNotIn("{ number: 6, label: \"6限\"", api)
        columns = css.split(".timetable-page .timetable-grid")[1].split(
            ".timetable-page .timetable-od-panel"
        )[0]
        self.assertIn("grid-template-columns: var(--tt-period-w) repeat(", columns)
        self.assertIn("var(--tt-day-min)", columns)
        self.assertIn(
            "grid-template-rows: var(--tt-head-h) repeat(",
            columns,
        )
        self.assertIn("minmax(var(--tt-row-min), 1fr)", columns)
        self.assertNotIn("aspect-ratio", columns)
        self.assertNotIn("88px", css.split(".timetable-page .timetable-layout")[1].split(
            ".timetable-page .timetable-grid"
        )[0])

    def test_mobile_week_grid_uses_definite_available_height(self):
        css = _read("frontend/src/styles/timetable.css")
        page = _read("frontend/src/pages/TimetablePage.tsx")
        self.assertIn("--tt-available-h:", css)
        self.assertIn("100dvh", css)
        self.assertIn("var(--nav-h, 56px)", css)
        self.assertIn("env(safe-area-inset-bottom, 0px)", css)
        self.assertIn("@media (max-width: 1023px)", css)
        mobile = css.split("@media (max-width: 1023px)")[1].split("@media (min-width: 600px)")[0]
        self.assertIn(".has-week-grid .main-inner--timetable", mobile)
        self.assertIn("height: var(--tt-available-h)", mobile)
        self.assertIn("max-height: var(--tt-available-h)", mobile)
        self.assertIn(":not(.is-embedded)", mobile)
        self.assertIn("has-week-grid", page)
        self.assertIn("is-embedded", page)
        desktop = css.split("@media (min-width: 1024px)")[1].split("/* Modal")[0]
        self.assertIn("height: auto", desktop)
        self.assertIn("max-height: none", desktop)
        self.assertNotIn("100px", mobile)

    def test_empty_cells_stay_centered_and_od_column_still_independent(self):
        css = _read("frontend/src/styles/timetable.css")
        self.assertIn(".timetable-page .timetable-slot.is-empty", css)
        empty = css.split(".timetable-page .timetable-slot.is-empty")[1].split("}")[0]
        self.assertIn("align-items: center", empty)
        self.assertIn("justify-content: center", empty)
        self.assertIn(".timetable-od-panel", css)
        self.assertIn("--tt-od-min: 108px", css)
        self.assertIn("has-more::after", css)
        self.assertIn("width: max-content", css.split(".timetable-page .timetable-layout")[1].split(
            ".timetable-page .timetable-grid"
        )[0])

    def test_calendar_and_own_other_contracts_unchanged(self):
        css = _read("frontend/src/styles/timetable.css")
        page = _read("frontend/src/pages/TimetablePage.tsx")
        surface = _read("frontend/src/features/timetable/surface.ts")
        transition = _read("frontend/src/lib/detailTransition.ts")
        keep = _read("frontend/src/layouts/TabKeepAliveLayout.tsx")
        self.assertIn(".tt-calendar", css)
        self.assertIn("showSectionTabs = !viewingOther", page)
        self.assertIn("<TimetablePage ignoreRouteUserPk />", keep)
        self.assertIn("if (input.ignoreRouteUserPk) return undefined", surface)
        self.assertIn("export function syncMainTabWindowScroll", transition)
        calendar_src = page.split(
            ") : showSectionTabs && section === \"calendar\" ? ("
        )[1]
        self.assertIn("<TimetableCalendarView", calendar_src)


