import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link } from "react-router-dom";
import { spaLoginPath } from "../auth/api";
import {
  TIMETABLE_OD_SLOTS,
  TIMETABLE_PERIODS,
  type SlotsMap,
} from "../timetable/api";
import {
  createAbsenceRecord,
  deleteAbsenceRecord,
  fetchOfferingAttendance,
  type CourseAttendancePayload,
} from "../courses/api";
import {
  createCalendarEvent,
  createCourseCalendarException,
  defaultCalendarCategories,
  deleteCalendarEvent,
  deleteCourseCalendarException,
  fetchCalendarMonth,
  fetchCourseCalendarExceptions,
  formatDayHeading,
  formatMonthTitle,
  formatShortDate,
  jsWeekdayToTimetableDayIndex,
  parseDateKey,
  toDateKey,
  updateCalendarEvent,
  type CalendarEvent,
  type CalendarDot,
  type CalendarEventInput,
  type CourseCalendarException,
} from "./api";
import { analytics } from "../../lib/analytics";

type ClassItem = {
  key: string;
  timeLabel: string;
  periodLabel: string;
  name: string;
  room: string;
  offeringId: number | null;
  source: "timetable";
};

type Props = {
  slots: SlotsMap;
  authenticated: boolean;
};

type UndoToast =
  | {
      kind: "exception";
      message: string;
      exceptionId: number;
      offeringId: number;
      date: string;
    }
  | {
      kind: "absence";
      message: string;
      recordId: number;
      offeringId: number;
      date: string;
    };

function buildMonthCells(year: number, month: number) {
  const first = new Date(year, month - 1, 1);
  const startPad = first.getDay(); // Sun=0
  const daysInMonth = new Date(year, month, 0).getDate();
  const cells: Array<{ dateKey: string | null; day: number | null }> = [];
  for (let i = 0; i < startPad; i += 1) {
    cells.push({ dateKey: null, day: null });
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    const key = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    cells.push({ dateKey: key, day });
  }
  while (cells.length % 7 !== 0) {
    cells.push({ dateKey: null, day: null });
  }
  return cells;
}

function classesForDate(dateKey: string, slots: SlotsMap): ClassItem[] {
  const d = parseDateKey(dateKey);
  const dayIndex = jsWeekdayToTimetableDayIndex(d.getDay());
  if (dayIndex == null) return [];
  const items: ClassItem[] = [];
  for (const period of TIMETABLE_PERIODS) {
    const slotKey = `p${period.number}-d${dayIndex}`;
    const entry = slots[slotKey];
    if (!entry?.name) continue;
    items.push({
      key: slotKey,
      timeLabel: period.time.split("-")[0] || period.label,
      periodLabel: period.label,
      name: entry.name,
      room: entry.room || "",
      offeringId: entry.offering_id ?? null,
      source: "timetable",
    });
  }
  for (const od of TIMETABLE_OD_SLOTS) {
    const slotKey = `od${od.number}-d${dayIndex}`;
    const entry = slots[slotKey];
    if (!entry?.name) continue;
    items.push({
      key: slotKey,
      timeLabel: od.label,
      periodLabel: od.label,
      name: entry.name,
      room: "",
      offeringId: entry.offering_id ?? null,
      source: "timetable",
    });
  }
  return items;
}

function emptyDraft(dateKey: string): CalendarEventInput {
  return {
    title: "",
    date: dateKey,
    start_time: "",
    end_time: "",
    memo: "",
    category: "other",
  };
}

function skippedKey(offeringId: number, dateKey: string) {
  return `${offeringId}:${dateKey}`;
}

export function TimetableCalendarView({ slots, authenticated }: Props) {
  const todayKey = useMemo(() => toDateKey(new Date()), []);
  const [cursor, setCursor] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() + 1 };
  });
  const [selectedKey, setSelectedKey] = useState(todayKey);
  const [dots, setDots] = useState<Record<string, CalendarDot>>({});
  const [byDate, setByDate] = useState<Record<string, CalendarEvent[]>>({});
  const [categories, setCategories] = useState(defaultCalendarCategories());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState<null | {
    mode: "create" | "edit";
    draft: CalendarEventInput;
    eventId?: number;
  }>(null);
  const [exceptions, setExceptions] = useState<CourseCalendarException[]>([]);
  const [classDetail, setClassDetail] = useState<ClassItem | null>(null);
  const [classAttendance, setClassAttendance] =
    useState<CourseAttendancePayload | null>(null);
  const [classAttendanceLoading, setClassAttendanceLoading] = useState(false);
  const [hiddenOpen, setHiddenOpen] = useState(false);
  const [hiddenList, setHiddenList] = useState<CourseCalendarException[]>([]);
  const [hiddenLoading, setHiddenLoading] = useState(false);
  const [toast, setToast] = useState<UndoToast | null>(null);
  const toastTimerRef = useRef<number | null>(null);

  const cells = useMemo(
    () => buildMonthCells(cursor.year, cursor.month),
    [cursor.year, cursor.month]
  );

  const skippedSet = useMemo(() => {
    const set = new Set<string>();
    for (const row of exceptions) {
      if (row.status === "skipped") {
        set.add(skippedKey(row.offering_id, row.date));
      }
    }
    return set;
  }, [exceptions]);

  const clearToastTimer = () => {
    if (toastTimerRef.current != null) {
      window.clearTimeout(toastTimerRef.current);
      toastTimerRef.current = null;
    }
  };

  const showUndoToast = (next: UndoToast) => {
    clearToastTimer();
    setToast(next);
    toastTimerRef.current = window.setTimeout(() => {
      setToast(null);
      toastTimerRef.current = null;
    }, 6000);
  };

  const loadMonth = useCallback(
    async (signal?: AbortSignal) => {
      if (!authenticated) {
        setDots({});
        setByDate({});
        setExceptions([]);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const data = await fetchCalendarMonth(
          cursor.year,
          cursor.month,
          signal
        );
        if (signal?.aborted) return;
        setDots(data.dots || {});
        setByDate(data.by_date || {});
        setExceptions(data.course_exceptions || []);
        if (data.categories?.length) setCategories(data.categories);
      } catch (err) {
        if ((err as Error)?.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "load_failed");
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [authenticated, cursor.year, cursor.month]
  );

  useEffect(() => {
    const ac = new AbortController();
    void loadMonth(ac.signal);
    return () => ac.abort();
  }, [loadMonth]);

  useEffect(() => {
    return () => clearToastTimer();
  }, []);

  useEffect(() => {
    if (!classDetail?.offeringId || !authenticated) {
      setClassAttendance(null);
      setClassAttendanceLoading(false);
      return;
    }
    const offeringId = classDetail.offeringId;
    let cancelled = false;
    setClassAttendanceLoading(true);
    void fetchOfferingAttendance(offeringId)
      .then((data) => {
        if (!cancelled) setClassAttendance(data);
      })
      .catch(() => {
        if (!cancelled) setClassAttendance(null);
      })
      .finally(() => {
        if (!cancelled) setClassAttendanceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [classDetail, authenticated]);

  useEffect(() => {
    // Keep selection in-range when month changes; prefer today if in this month.
    const [sy, sm] = selectedKey.split("-").map(Number);
    if (sy === cursor.year && sm === cursor.month) return;
    const [ty, tm] = todayKey.split("-").map(Number);
    if (ty === cursor.year && tm === cursor.month) {
      setSelectedKey(todayKey);
    } else {
      setSelectedKey(
        `${cursor.year}-${String(cursor.month).padStart(2, "0")}-01`
      );
    }
  }, [cursor.year, cursor.month, selectedKey, todayKey]);

  const dayEvents = byDate[selectedKey] || [];
  const dayClasses = useMemo(() => {
    return classesForDate(selectedKey, slots).filter((item) => {
      if (item.offeringId == null) return true;
      return !skippedSet.has(skippedKey(item.offeringId, selectedKey));
    });
  }, [selectedKey, slots, skippedSet]);

  const shiftMonth = (delta: number) => {
    setCursor((prev) => {
      const d = new Date(prev.year, prev.month - 1 + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() + 1 };
    });
  };

  const goToday = () => {
    const now = new Date();
    setCursor({ year: now.getFullYear(), month: now.getMonth() + 1 });
    setSelectedKey(todayKey);
  };

  const openCreate = () => {
    if (!authenticated) return;
    setEditor({ mode: "create", draft: emptyDraft(selectedKey) });
  };

  const openEdit = (event: CalendarEvent) => {
    setEditor({
      mode: "edit",
      eventId: event.id,
      draft: {
        title: event.title,
        date: event.date,
        start_time: event.start_time || "",
        end_time: event.end_time || "",
        memo: event.memo || "",
        category: event.category || "other",
      },
    });
  };

  const closeEditor = () => setEditor(null);

  const onSaveEditor = async (e: FormEvent) => {
    e.preventDefault();
    if (!editor) return;
    const title = editor.draft.title.trim();
    if (!title) {
      window.alert("予定名を入力してください。");
      return;
    }
    setBusy(true);
    try {
      if (editor.mode === "create") {
        await createCalendarEvent({
          ...editor.draft,
          title,
        });
      } else if (editor.eventId) {
        await updateCalendarEvent(editor.eventId, {
          ...editor.draft,
          title,
        });
      }
      closeEditor();
      await loadMonth();
      if (editor.draft.date) setSelectedKey(editor.draft.date);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "保存に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (event: CalendarEvent) => {
    if (!window.confirm(`「${event.title}」を削除しますか？`)) return;
    setBusy(true);
    try {
      await deleteCalendarEvent(event.id);
      await loadMonth();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "削除に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const onSkipClass = async (item: ClassItem) => {
    if (!item.offeringId) {
      window.alert("この授業は時間割の履修紐付けがないため、非表示にできません。");
      return;
    }
    setBusy(true);
    try {
      const exc = await createCourseCalendarException({
        offering_id: item.offeringId,
        date: selectedKey,
        status: "skipped",
      });
      analytics.courseCalendarEventSkipped({
        offering_id: item.offeringId,
        date: selectedKey,
        source: "event_detail",
      });
      setClassDetail(null);
      setExceptions((prev) => {
        const without = prev.filter(
          (row) =>
            !(
              row.offering_id === exc.offering_id &&
              row.date === exc.date
            )
        );
        return [...without, exc];
      });
      showUndoToast({
        kind: "exception",
        message: `${formatShortDate(selectedKey)}の${item.name}を非表示にしました`,
        exceptionId: exc.id,
        offeringId: item.offeringId,
        date: selectedKey,
      });
    } catch (err) {
      window.alert(
        err instanceof Error ? err.message : "非表示に失敗しました"
      );
    } finally {
      setBusy(false);
    }
  };

  const onRestoreException = async (
    exception: CourseCalendarException,
    source: "undo_toast" | "hidden_events_list"
  ) => {
    setBusy(true);
    try {
      await deleteCourseCalendarException(exception.id);
      analytics.courseCalendarEventRestored({
        offering_id: exception.offering_id,
        date: exception.date,
        source,
      });
      setExceptions((prev) => prev.filter((row) => row.id !== exception.id));
      setHiddenList((prev) => prev.filter((row) => row.id !== exception.id));
      if (toast?.kind === "exception" && toast.exceptionId === exception.id) {
        clearToastTimer();
        setToast(null);
      }
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "復元に失敗しました");
    } finally {
      setBusy(false);
    }
  };

  const openHiddenList = async () => {
    if (!authenticated) return;
    setHiddenOpen(true);
    setHiddenLoading(true);
    try {
      const rows = await fetchCourseCalendarExceptions();
      setHiddenList(rows);
    } catch (err) {
      window.alert(
        err instanceof Error ? err.message : "一覧の取得に失敗しました"
      );
      setHiddenOpen(false);
    } finally {
      setHiddenLoading(false);
    }
  };

  const onMarkAbsence = async (item: ClassItem) => {
    if (!item.offeringId) return;
    setBusy(true);
    try {
      const result = await createAbsenceRecord(item.offeringId, selectedKey);
      setClassAttendance(result.attendance);
      analytics.courseAbsenceRecorded({
        offering_id: item.offeringId,
        date: selectedKey,
        source: "calendar",
      });
      showUndoToast({
        kind: "absence",
        message: `${formatShortDate(selectedKey)}を欠席として記録しました`,
        recordId: result.record.id,
        offeringId: item.offeringId,
        date: selectedKey,
      });
    } catch (err) {
      const code = err instanceof Error ? err.message : "";
      if (code === "date_calendar_skipped") {
        window.alert(
          "この日は予定を非表示にしています。欠席記録はできません。"
        );
      } else if (code === "current_enrollment_required") {
        window.alert("履修中の授業のみ欠席を記録できます。");
      } else {
        window.alert(
          err instanceof Error ? err.message : "欠席の記録に失敗しました"
        );
      }
    } finally {
      setBusy(false);
    }
  };

  const onRemoveAbsenceFromCalendar = async (
    recordId: number,
    offeringId: number,
    date: string,
    source: "calendar" | "undo"
  ) => {
    setBusy(true);
    try {
      const result = await deleteAbsenceRecord(recordId);
      if (result.attendance) setClassAttendance(result.attendance);
      else {
        setClassAttendance((prev) =>
          prev
            ? {
                ...prev,
                records: prev.records.filter((r) => r.id !== recordId),
                absence_count: Math.max(0, prev.absence_count - 1),
              }
            : prev
        );
      }
      analytics.courseAbsenceRemoved({
        offering_id: offeringId,
        date,
        source,
      });
      if (toast?.kind === "absence" && toast.recordId === recordId) {
        clearToastTimer();
        setToast(null);
      }
    } catch (err) {
      window.alert(
        err instanceof Error ? err.message : "欠席記録の取消に失敗しました"
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="tt-calendar" aria-label="カレンダー">
      <div className="tt-calendar__nav">
        <button
          type="button"
          className="tt-calendar__nav-btn"
          aria-label="前月"
          onClick={() => shiftMonth(-1)}
        >
          ‹
        </button>
        <h2 className="tt-calendar__month-title">
          {formatMonthTitle(cursor.year, cursor.month)}
        </h2>
        <button
          type="button"
          className="tt-calendar__nav-btn"
          aria-label="翌月"
          onClick={() => shiftMonth(1)}
        >
          ›
        </button>
        <button
          type="button"
          className="tt-calendar__today-btn"
          onClick={goToday}
        >
          今日
        </button>
      </div>

      <div className="tt-calendar__weekdays" aria-hidden="true">
        {["日", "月", "火", "水", "木", "金", "土"].map((w) => (
          <span key={w} className="tt-calendar__weekday">
            {w}
          </span>
        ))}
      </div>

      <div className="tt-calendar__grid" role="grid" aria-label="月間カレンダー">
        {cells.map((cell, idx) => {
          if (!cell.dateKey) {
            return (
              <div
                key={`pad-${idx}`}
                className="tt-calendar__cell is-pad"
                aria-hidden="true"
              />
            );
          }
          const dot = dots[cell.dateKey];
          const isSelected = cell.dateKey === selectedKey;
          const isToday = cell.dateKey === todayKey;
          return (
            <button
              key={cell.dateKey}
              type="button"
              role="gridcell"
              className={`tt-calendar__cell${isSelected ? " is-selected" : ""}${
                isToday ? " is-today" : ""
              }`}
              aria-label={`${cell.day}日${dot ? `、予定${dot.count}件` : ""}`}
              aria-pressed={isSelected}
              onClick={() => setSelectedKey(cell.dateKey!)}
            >
              <span className="tt-calendar__day-num">{cell.day}</span>
              {dot ? (
                <span className="tt-calendar__marks">
                  {dot.titles[0] ? (
                    <span className="tt-calendar__mark-title">
                      {dot.titles[0]}
                    </span>
                  ) : (
                    <span className="tt-calendar__dot" />
                  )}
                  {dot.count > 1 ? (
                    <span className="tt-calendar__extra">+{dot.count - 1}</span>
                  ) : null}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      <div className="tt-calendar__agenda">
        <header className="tt-calendar__agenda-head">
          <h3>{formatDayHeading(selectedKey)}</h3>
          <div className="tt-calendar__agenda-actions">
            {authenticated ? (
              <button
                type="button"
                className="tt-calendar__link-btn"
                onClick={() => void openHiddenList()}
              >
                非表示にした予定
              </button>
            ) : null}
            {authenticated ? (
              <button
                type="button"
                className="tt-calendar__add-btn"
                onClick={openCreate}
              >
                ＋ 予定を追加
              </button>
            ) : null}
          </div>
        </header>

        {!authenticated ? (
          <p className="tt-calendar__note">
            <Link to={spaLoginPath("/app/timetable")}>ログイン</Link>
            すると予定を保存できます。時間割の授業は下に表示されます。
          </p>
        ) : null}

        {loading ? <p className="tt-calendar__note">読み込み中…</p> : null}
        {error ? (
          <p className="tt-calendar__note">読み込みに失敗しました（{error}）</p>
        ) : null}

        {!loading && dayClasses.length === 0 && dayEvents.length === 0 ? (
          <p className="tt-calendar__empty">この日の予定はありません</p>
        ) : null}

        <ul className="tt-calendar__list">
          {dayClasses.map((item) => (
            <li key={item.key} className="tt-calendar__item is-class">
              <button
                type="button"
                className="tt-calendar__item-btn"
                onClick={() => setClassDetail(item)}
              >
                <span className="tt-calendar__item-time">
                  {item.timeLabel}
                  <span className="tt-calendar__item-period">
                    {item.periodLabel}
                  </span>
                </span>
                <span className="tt-calendar__item-body">
                  <strong>{item.name}</strong>
                  {item.room ? (
                    <span className="tt-calendar__item-meta">{item.room}</span>
                  ) : null}
                  <span className="tt-calendar__item-badge">時間割</span>
                </span>
              </button>
            </li>
          ))}
          {dayEvents.map((event) => (
            <li key={event.id} className="tt-calendar__item is-event">
              <button
                type="button"
                className="tt-calendar__item-btn"
                onClick={() => openEdit(event)}
              >
                <span className="tt-calendar__item-time">
                  {event.start_time || "終日"}
                  {event.end_time ? `–${event.end_time}` : ""}
                </span>
                <span className="tt-calendar__item-body">
                  <strong>{event.title}</strong>
                  <span className="tt-calendar__item-meta">
                    {event.category_label}
                    {event.memo ? ` · ${event.memo}` : ""}
                  </span>
                </span>
              </button>
              <button
                type="button"
                className="tt-calendar__item-delete"
                aria-label={`${event.title}を削除`}
                disabled={busy}
                onClick={() => void onDelete(event)}
              >
                削除
              </button>
            </li>
          ))}
        </ul>
      </div>

      {editor ? (
        <div className="compose-modal" aria-hidden="false">
          <div
            className="compose-modal__backdrop"
            onClick={closeEditor}
          />
          <div
            className="compose-modal__panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="tt-calendar-event-title"
          >
            <header className="compose-modal__header">
              <h2 id="tt-calendar-event-title">
                {editor.mode === "create" ? "予定を追加" : "予定を編集"}
              </h2>
              <button
                type="button"
                className="compose-modal__close"
                aria-label="閉じる"
                onClick={closeEditor}
              >
                ×
              </button>
            </header>
            <form onSubmit={(e) => void onSaveEditor(e)} noValidate>
              <div className="compose-image-field">
                <label htmlFor="cal-event-title">予定名</label>
                <input
                  id="cal-event-title"
                  type="text"
                  maxLength={120}
                  required
                  value={editor.draft.title}
                  onChange={(e) =>
                    setEditor((prev) =>
                      prev
                        ? {
                            ...prev,
                            draft: { ...prev.draft, title: e.target.value },
                          }
                        : prev
                    )
                  }
                  autoFocus
                />
              </div>
              <div className="compose-image-field">
                <label htmlFor="cal-event-date">日付</label>
                <input
                  id="cal-event-date"
                  type="date"
                  required
                  value={editor.draft.date}
                  onChange={(e) =>
                    setEditor((prev) =>
                      prev
                        ? {
                            ...prev,
                            draft: { ...prev.draft, date: e.target.value },
                          }
                        : prev
                    )
                  }
                />
              </div>
              <div className="tt-calendar__time-row">
                <div className="compose-image-field">
                  <label htmlFor="cal-event-start">開始</label>
                  <input
                    id="cal-event-start"
                    type="time"
                    value={editor.draft.start_time || ""}
                    onChange={(e) =>
                      setEditor((prev) =>
                        prev
                          ? {
                              ...prev,
                              draft: {
                                ...prev.draft,
                                start_time: e.target.value,
                              },
                            }
                          : prev
                      )
                    }
                  />
                </div>
                <div className="compose-image-field">
                  <label htmlFor="cal-event-end">終了</label>
                  <input
                    id="cal-event-end"
                    type="time"
                    value={editor.draft.end_time || ""}
                    onChange={(e) =>
                      setEditor((prev) =>
                        prev
                          ? {
                              ...prev,
                              draft: {
                                ...prev.draft,
                                end_time: e.target.value,
                              },
                            }
                          : prev
                      )
                    }
                  />
                </div>
              </div>
              <div className="compose-image-field">
                <label htmlFor="cal-event-category">カテゴリ</label>
                <select
                  id="cal-event-category"
                  value={editor.draft.category || "other"}
                  onChange={(e) =>
                    setEditor((prev) =>
                      prev
                        ? {
                            ...prev,
                            draft: {
                              ...prev.draft,
                              category: e.target.value,
                            },
                          }
                        : prev
                    )
                  }
                >
                  {categories.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="compose-image-field">
                <label htmlFor="cal-event-memo">メモ</label>
                <textarea
                  id="cal-event-memo"
                  maxLength={2000}
                  rows={3}
                  value={editor.draft.memo || ""}
                  onChange={(e) =>
                    setEditor((prev) =>
                      prev
                        ? {
                            ...prev,
                            draft: { ...prev.draft, memo: e.target.value },
                          }
                        : prev
                    )
                  }
                />
              </div>
              <div className="timetable-modal-actions">
                {editor.mode === "edit" && editor.eventId ? (
                  <button
                    type="button"
                    className="btn-timetable-clear"
                    disabled={busy}
                    onClick={() => {
                      const ev = dayEvents.find((x) => x.id === editor.eventId);
                      if (ev) void onDelete(ev);
                      closeEditor();
                    }}
                  >
                    削除
                  </button>
                ) : (
                  <span />
                )}
                <button type="submit" className="btn-compose" disabled={busy}>
                  保存
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {classDetail ? (
        <div className="compose-modal" aria-hidden="false">
          <div
            className="compose-modal__backdrop"
            onClick={() => setClassDetail(null)}
          />
          <div
            className="compose-modal__panel tt-calendar__class-sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="tt-calendar-class-title"
          >
            <header className="compose-modal__header">
              <h2 id="tt-calendar-class-title">{classDetail.name}</h2>
              <button
                type="button"
                className="compose-modal__close"
                aria-label="閉じる"
                onClick={() => setClassDetail(null)}
              >
                ×
              </button>
            </header>
            <div className="tt-calendar__class-sheet-body">
              <p className="tt-calendar__class-meta">
                {formatDayHeading(selectedKey)} · {classDetail.periodLabel}
                {classDetail.room ? ` · ${classDetail.room}` : ""}
              </p>
              {classDetail.offeringId ? (
                <div className="tt-calendar__absence-block">
                  {classAttendanceLoading ? (
                    <p className="tt-calendar__class-hint">欠席情報を読み込み中…</p>
                  ) : classAttendance ? (
                    <>
                      <p className="tt-calendar__absence-count">
                        欠席 {classAttendance.absence_count}回
                      </p>
                      {(() => {
                        const todayRecord = classAttendance.records.find(
                          (r) => r.date === selectedKey
                        );
                        if (todayRecord) {
                          return (
                            <div className="tt-calendar__absence-actions">
                              <p className="tt-calendar__absence-marked">
                                ✓ この日は欠席として記録されています
                              </p>
                              <button
                                type="button"
                                className="tt-calendar__absence-undo"
                                disabled={busy}
                                onClick={() =>
                                  void onRemoveAbsenceFromCalendar(
                                    todayRecord.id,
                                    classDetail.offeringId!,
                                    selectedKey,
                                    "calendar"
                                  )
                                }
                              >
                                欠席記録を取り消す
                              </button>
                            </div>
                          );
                        }
                        if (classAttendance.can_record) {
                          return (
                            <button
                              type="button"
                              className="tt-calendar__absence-btn"
                              disabled={busy}
                              onClick={() => void onMarkAbsence(classDetail)}
                            >
                              この授業を欠席にする
                            </button>
                          );
                        }
                        return (
                          <p className="tt-calendar__class-hint">
                            履修中のみ欠席を記録できます。
                          </p>
                        );
                      })()}
                    </>
                  ) : (
                    <p className="tt-calendar__class-hint">
                      欠席記録は履修中（または過去履修）の授業で利用できます。
                    </p>
                  )}
                </div>
              ) : null}
              <p className="tt-calendar__class-hint">
                時間割には残ります。この日のカレンダー表示だけ消えます。
              </p>
              {classDetail.offeringId ? (
                <Link
                  className="tt-calendar__class-link"
                  to={`/courses/${classDetail.offeringId}`}
                  onClick={() => setClassDetail(null)}
                >
                  授業詳細を開く
                </Link>
              ) : null}
              <button
                type="button"
                className="tt-calendar__skip-btn"
                disabled={busy || !classDetail.offeringId}
                onClick={() => void onSkipClass(classDetail)}
              >
                この日の予定を非表示
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {hiddenOpen ? (
        <div className="compose-modal" aria-hidden="false">
          <div
            className="compose-modal__backdrop"
            onClick={() => setHiddenOpen(false)}
          />
          <div
            className="compose-modal__panel tt-calendar__hidden-sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="tt-calendar-hidden-title"
          >
            <header className="compose-modal__header">
              <h2 id="tt-calendar-hidden-title">非表示にした予定</h2>
              <button
                type="button"
                className="compose-modal__close"
                aria-label="閉じる"
                onClick={() => setHiddenOpen(false)}
              >
                ×
              </button>
            </header>
            <div className="tt-calendar__hidden-body">
              {hiddenLoading ? (
                <p className="tt-calendar__note">読み込み中…</p>
              ) : hiddenList.length === 0 ? (
                <p className="tt-calendar__empty">非表示の予定はありません</p>
              ) : (
                <ul className="tt-calendar__hidden-list">
                  {hiddenList.map((row) => (
                    <li key={row.id} className="tt-calendar__hidden-item">
                      <div>
                        <strong>{formatShortDate(row.date)}</strong>
                        <span>{row.offering_title || "授業"}</span>
                        {row.instructor ? (
                          <span className="tt-calendar__item-meta">
                            {row.instructor}
                          </span>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        className="tt-calendar__restore-btn"
                        disabled={busy}
                        onClick={() =>
                          void onRestoreException(row, "hidden_events_list")
                        }
                      >
                        復元
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {toast ? (
        <div className="tt-calendar__toast" role="status">
          <span>{toast.message}</span>
          <button
            type="button"
            className="tt-calendar__toast-undo"
            disabled={busy}
            onClick={() => {
              if (toast.kind === "exception") {
                void onRestoreException(
                  {
                    id: toast.exceptionId,
                    offering_id: toast.offeringId,
                    date: toast.date,
                    status: "skipped",
                    offering_title: "",
                    instructor: "",
                  },
                  "undo_toast"
                );
              } else {
                void onRemoveAbsenceFromCalendar(
                  toast.recordId,
                  toast.offeringId,
                  toast.date,
                  "undo"
                );
              }
            }}
          >
            元に戻す
          </button>
        </div>
      ) : null}
    </section>
  );
}
