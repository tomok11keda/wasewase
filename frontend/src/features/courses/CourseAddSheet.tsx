import { useEffect, useRef, useState } from "react";
import {
  createOffering,
  enrollOffering,
  fetchCourseMeta,
  offeringScheduleText,
  searchCourses,
  type CourseMeta,
  type CourseOffering,
  type SlotPayload,
} from "./api";
import { analytics } from "../../lib/analytics/events";

export type CourseAddContext = {
  /** 空きセルから開いた場合 */
  slotKey?: string | null;
  dayOfWeek?: number | null;
  period?: number | null;
  periodKind?: "period" | "od" | string | null;
  dayLabel?: string;
  periodLabel?: string;
  /** グローバル「＋授業を追加」なら true → 追加後もシートを開いたまま */
  continuous?: boolean;
};

type Props = {
  open: boolean;
  context: CourseAddContext;
  onClose: () => void;
  onAdded: (slot: SlotPayload, offering: CourseOffering) => void;
  onFreeText: (ctx: CourseAddContext) => void;
};

type Mode = "search" | "create" | "duplicates";

function useDebounced(value: string, ms: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

export function CourseAddSheet({
  open,
  context,
  onClose,
  onAdded,
  onFreeText,
}: Props) {
  const [mode, setMode] = useState<Mode>("search");
  const [query, setQuery] = useState("");
  const debouncedQ = useDebounced(query, 220);
  const [results, setResults] = useState<CourseOffering[]>([]);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [meta, setMeta] = useState<CourseMeta | null>(null);
  const [duplicates, setDuplicates] = useState<CourseOffering[]>([]);
  const [pendingCreate, setPendingCreate] = useState<Record<
    string,
    string | number
  > | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const [form, setForm] = useState({
    title: "",
    instructor: "",
    semester: "spring",
    academic_year: new Date().getFullYear(),
    day_of_week: 0,
    period: 1,
    period_kind: "period",
    school: "",
    campus: "",
    room: "",
    credits: "",
  });

  useEffect(() => {
    if (!open) return;
    setMode("search");
    setQuery("");
    setResults([]);
    setDuplicates([]);
    setPendingCreate(null);
    setToast(null);
    analytics.courseSearchOpened({
      from_slot: Boolean(context.slotKey),
    });
    void fetchCourseMeta()
      .then((m) => {
        setMeta(m);
        setForm((f) => ({
          ...f,
          semester: m.semester,
          academic_year: m.academic_year,
          day_of_week: context.dayOfWeek ?? 0,
          period: context.period ?? 1,
          period_kind: context.periodKind || "period",
          title: "",
          instructor: "",
          school: "",
          campus: "",
          room: "",
          credits: "",
        }));
      })
      .catch(() => {
        /* ignore */
      });
    const t = window.setTimeout(() => inputRef.current?.focus(), 80);
    return () => window.clearTimeout(t);
  }, [open, context.slotKey, context.dayOfWeek, context.period, context.periodKind]);

  useEffect(() => {
    if (!open || mode !== "search") return;
    let cancelled = false;
    setSearching(true);
    void searchCourses({
      q: debouncedQ,
      day: context.dayOfWeek,
      period: context.period,
      period_kind: context.periodKind,
      semester: meta?.semester,
      year: meta?.academic_year,
    })
      .then((rows) => {
        if (!cancelled) {
          setResults(rows);
          if (debouncedQ.trim()) {
            analytics.courseSearchPerformed({
              query_len: debouncedQ.trim().length,
              result_count: rows.length,
            });
          }
        }
      })
      .catch(() => {
        if (!cancelled) setResults([]);
      })
      .finally(() => {
        if (!cancelled) setSearching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    open,
    mode,
    debouncedQ,
    context.dayOfWeek,
    context.period,
    context.periodKind,
    meta?.semester,
    meta?.academic_year,
  ]);

  useEffect(() => {
    if (!open) {
      document.body.classList.remove("course-sheet-open");
      return;
    }
    document.body.classList.add("course-sheet-open");
    return () => document.body.classList.remove("course-sheet-open");
  }, [open]);

  if (!open) return null;

  const contextHint =
    context.dayLabel && context.periodLabel
      ? `${context.dayLabel}曜・${context.periodLabel}`
      : null;

  const showToast = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 1800);
  };

  const handleEnroll = async (offering: CourseOffering) => {
    setBusy(true);
    try {
      const data = await enrollOffering(offering.id, context.slotKey);
      analytics.existingCourseAdded({
        from_slot: Boolean(context.slotKey),
      });
      onAdded(data.slot, data.offering);
      showToast("授業を追加しました");
      if (context.continuous) {
        setQuery("");
        setMode("search");
        inputRef.current?.focus();
      } else {
        window.setTimeout(() => onClose(), 350);
      }
    } catch {
      window.alert("時間割への追加に失敗しました。もう一度お試しください。");
    } finally {
      setBusy(false);
    }
  };

  const submitCreate = async (force = false) => {
    if (!form.title.trim() || !form.instructor.trim()) {
      window.alert("授業名と担当教員名を入力してください。");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        title: form.title.trim(),
        instructor: form.instructor.trim(),
        academic_year: Number(form.academic_year),
        semester: form.semester,
        day_of_week: Number(form.day_of_week),
        period: Number(form.period),
        period_kind: String(form.period_kind),
        school: form.school,
        campus: form.campus,
        room: form.room,
        credits: form.credits,
        slot_key: context.slotKey || null,
        enroll: true,
        force_create: force,
      };
      const data = await createOffering(payload);
      if (data.error === "duplicate_candidates" && data.duplicates?.length) {
        setDuplicates(data.duplicates);
        setPendingCreate(payload as unknown as Record<string, string | number>);
        setMode("duplicates");
        return;
      }
      if (!data.ok || !data.offering || !data.slot) {
        window.alert("授業の作成に失敗しました。");
        return;
      }
      analytics.newCourseCreated({ forced: force });
      onAdded(data.slot, data.offering);
      showToast("新しい授業を追加しました");
      if (context.continuous) {
        setMode("search");
        setQuery("");
        setForm((f) => ({ ...f, title: "", instructor: "", room: "", credits: "" }));
      } else {
        window.setTimeout(() => onClose(), 350);
      }
    } catch {
      window.alert("授業の作成に失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="course-sheet" role="dialog" aria-modal="true">
      <button
        type="button"
        className="course-sheet__backdrop"
        aria-label="閉じる"
        onClick={onClose}
      />
      <div className="course-sheet__panel">
        <header className="course-sheet__header">
          <div>
            <h2 className="course-sheet__title">授業を追加</h2>
            {contextHint ? (
              <p className="course-sheet__hint">{contextHint}</p>
            ) : (
              <p className="course-sheet__hint">授業名・教員名で検索</p>
            )}
          </div>
          <button
            type="button"
            className="course-sheet__close"
            aria-label="閉じる"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        {toast ? <div className="course-sheet__toast">{toast}</div> : null}

        {mode === "search" ? (
          <>
            <div className="course-sheet__search">
              <input
                ref={inputRef}
                type="search"
                enterKeyHint="search"
                placeholder="授業名・担当教員で検索"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                autoComplete="off"
                autoCorrect="off"
                spellCheck={false}
              />
            </div>
            <div className="course-sheet__results">
              {searching ? (
                <p className="course-sheet__empty">検索中…</p>
              ) : results.length === 0 ? (
                <p className="course-sheet__empty">
                  {query.trim()
                    ? "該当する授業がありません"
                    : contextHint
                      ? `${contextHint}の候補を表示しています`
                      : "キーワードを入力して検索"}
                </p>
              ) : (
                <ul className="course-sheet__list">
                  {results.map((o) => (
                    <li key={o.id}>
                      <button
                        type="button"
                        className="course-sheet__item"
                        disabled={busy}
                        onClick={() => void handleEnroll(o)}
                      >
                        <span className="course-sheet__item-title">
                          {o.title}
                        </span>
                        <span className="course-sheet__item-meta">
                          {o.instructor}
                          {" · "}
                          {offeringScheduleText(o)}
                          {o.enrollment_count > 0
                            ? ` · 履修中 ${o.enrollment_count}人`
                            : ""}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <div className="course-sheet__footer-actions">
                <button
                  type="button"
                  className="course-sheet__secondary"
                  onClick={() => {
                    setForm((f) => ({
                      ...f,
                      title: query.trim() || f.title,
                    }));
                    setMode("create");
                  }}
                >
                  ＋ 新しい授業を追加
                </button>
                {context.slotKey ? (
                  <button
                    type="button"
                    className="course-sheet__linkish"
                    onClick={() => onFreeText(context)}
                  >
                    自由入力する
                  </button>
                ) : null}
              </div>
            </div>
          </>
        ) : null}

        {mode === "create" ? (
          <div className="course-sheet__form">
            <button
              type="button"
              className="course-sheet__back"
              onClick={() => setMode("search")}
            >
              ← 検索に戻る
            </button>
            <label>
              授業名
              <input
                value={form.title}
                onChange={(e) =>
                  setForm((f) => ({ ...f, title: e.target.value }))
                }
                maxLength={80}
                autoFocus
              />
            </label>
            <label>
              担当教員名
              <input
                value={form.instructor}
                onChange={(e) =>
                  setForm((f) => ({ ...f, instructor: e.target.value }))
                }
                maxLength={80}
              />
            </label>
            <div className="course-sheet__row">
              <label>
                学期
                <select
                  value={form.semester}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, semester: e.target.value }))
                  }
                >
                  {(meta?.semesters || []).map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                年度
                <input
                  type="number"
                  value={form.academic_year}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      academic_year: Number(e.target.value),
                    }))
                  }
                />
              </label>
            </div>
            {context.slotKey ? (
              <p className="course-sheet__locked">
                曜時限: {contextHint}（セルから自動設定）
              </p>
            ) : (
              <div className="course-sheet__row">
                <label>
                  曜日
                  <select
                    value={form.day_of_week}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        day_of_week: Number(e.target.value),
                      }))
                    }
                  >
                    {["月", "火", "水", "木", "金", "土"].map((d, i) => (
                      <option key={d} value={i}>
                        {d}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  時限
                  <select
                    value={`${form.period_kind}:${form.period}`}
                    onChange={(e) => {
                      const [kind, num] = e.target.value.split(":");
                      setForm((f) => ({
                        ...f,
                        period_kind: kind,
                        period: Number(num),
                      }));
                    }}
                  >
                    {[1, 2, 3, 4, 5].map((n) => (
                      <option key={`p${n}`} value={`period:${n}`}>
                        {n}限
                      </option>
                    ))}
                    <option value="od:1">OD1</option>
                    <option value="od:2">OD2</option>
                  </select>
                </label>
              </div>
            )}
            <details className="course-sheet__optional">
              <summary>任意項目（学部・教室など）</summary>
              <label>
                学部
                <select
                  value={form.school}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, school: e.target.value }))
                  }
                >
                  <option value="">未設定</option>
                  {(meta?.faculties || []).map((f) => (
                    <option key={f.value} value={f.value}>
                      {f.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                キャンパス
                <select
                  value={form.campus}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, campus: e.target.value }))
                  }
                >
                  <option value="">未設定</option>
                  {(meta?.campuses || []).map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                教室
                <input
                  value={form.room}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, room: e.target.value }))
                  }
                />
              </label>
              <label>
                単位数
                <input
                  value={form.credits}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, credits: e.target.value }))
                  }
                />
              </label>
            </details>
            <button
              type="button"
              className="course-sheet__primary"
              disabled={busy}
              onClick={() => void submitCreate(false)}
            >
              時間割に追加
            </button>
          </div>
        ) : null}

        {mode === "duplicates" ? (
          <div className="course-sheet__form">
            <h3 className="course-sheet__dup-title">似ている授業があります</h3>
            <ul className="course-sheet__list">
              {duplicates.map((o) => (
                <li key={o.id}>
                  <button
                    type="button"
                    className="course-sheet__item"
                    disabled={busy}
                    onClick={() => void handleEnroll(o)}
                  >
                    <span className="course-sheet__item-title">{o.title}</span>
                    <span className="course-sheet__item-meta">
                      {o.instructor} · {offeringScheduleText(o)}
                    </span>
                    <span className="course-sheet__item-cta">
                      この授業を時間割に追加
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <button
              type="button"
              className="course-sheet__secondary"
              disabled={busy || !pendingCreate}
              onClick={() => void submitCreate(true)}
            >
              別の授業として新規作成
            </button>
            <button
              type="button"
              className="course-sheet__linkish"
              onClick={() => setMode("create")}
            >
              戻る
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
