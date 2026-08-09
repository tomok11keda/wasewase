import {
  useCallback,
  useEffect,
  useMemo,
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
  createCalendarEvent,
  defaultCalendarCategories,
  deleteCalendarEvent,
  fetchCalendarMonth,
  formatDayHeading,
  formatMonthTitle,
  jsWeekdayToTimetableDayIndex,
  parseDateKey,
  toDateKey,
  updateCalendarEvent,
  type CalendarEvent,
  type CalendarDot,
  type CalendarEventInput,
} from "./api";

type ClassItem = {
  key: string;
  timeLabel: string;
  periodLabel: string;
  name: string;
  room: string;
  source: "timetable";
};

type Props = {
  slots: SlotsMap;
  authenticated: boolean;
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

  const cells = useMemo(
    () => buildMonthCells(cursor.year, cursor.month),
    [cursor.year, cursor.month]
  );

  const loadMonth = useCallback(
    async (signal?: AbortSignal) => {
      if (!authenticated) {
        setDots({});
        setByDate({});
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
  const dayClasses = useMemo(
    () => classesForDate(selectedKey, slots),
    [selectedKey, slots]
  );

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
          {authenticated ? (
            <button
              type="button"
              className="tt-calendar__add-btn"
              onClick={openCreate}
            >
              ＋ 予定を追加
            </button>
          ) : null}
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
    </section>
  );
}
