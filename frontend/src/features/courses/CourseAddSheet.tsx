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
import {
  TIMETABLE_DAYS,
  type SlotsMap,
} from "../timetable/api";
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

type MeetingDraft = {
  day_of_week: number;
  period: number;
  period_kind: string;
  locked?: boolean;
};

type Props = {
  open: boolean;
  context: CourseAddContext;
  slots?: SlotsMap;
  onClose: () => void;
  onAdded: (slot: SlotPayload, offering: CourseOffering) => void;
  onFreeText: (ctx: CourseAddContext) => void;
};

type Mode = "search" | "create" | "duplicates";

function meetingIdentity(m: MeetingDraft): string {
  return `${m.period_kind}:${m.period}:d${m.day_of_week}`;
}

function meetingToSlotKey(m: MeetingDraft): string {
  const prefix = m.period_kind === "od" ? "od" : "p";
  return `${prefix}${m.period}-d${m.day_of_week}`;
}

function meetingLabel(m: MeetingDraft): string {
  const day = TIMETABLE_DAYS[m.day_of_week] || "?";
  if (m.period_kind === "od") return `${day}曜 OD${m.period}`;
  return `${day}曜 ${m.period}限`;
}

function defaultMeeting(ctx: CourseAddContext): MeetingDraft {
  return {
    day_of_week: ctx.dayOfWeek ?? 0,
    period: ctx.period ?? 1,
    period_kind: ctx.periodKind || "period",
    locked: Boolean(ctx.slotKey),
  };
}

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
  slots = {},
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
    unknown
  > | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const [form, setForm] = useState(() => {
    const now = new Date();
    const month = now.getMonth() + 1;
    const academicYear = month >= 4 ? now.getFullYear() : now.getFullYear() - 1;
    const semester = month >= 4 && month <= 9 ? "spring" : "fall";
    return {
      title: "",
      instructor: "",
      semester,
      academic_year: academicYear,
      school: "",
      campus: "",
      room: "",
      credits: "",
    };
  });
  const [meetings, setMeetings] = useState<MeetingDraft[]>(() => [
    defaultMeeting(context),
  ]);

  useEffect(() => {
    if (!open) return;
    setMode("search");
    setQuery("");
    setResults([]);
    setDuplicates([]);
    setPendingCreate(null);
    setToast(null);
    setMeetings([defaultMeeting(context)]);
    setForm((f) => ({
      ...f,
      title: "",
      instructor: "",
      school: "",
      campus: "",
      room: "",
      credits: "",
    }));
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
        }));
      })
      .catch(() => {
        /* meta 失敗でもセル由来の曜時限は meetings にセット済み */
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

  const createErrorMessage = (code: string | undefined, status?: number) => {
    switch (code) {
      case "duplicate_candidates":
        return "似ている授業があります。候補から選ぶか、別授業として作成してください。";
      case "slot_conflict":
        return "選択した曜日・時限に、すでに別の授業が入っています。";
      case "slot_mismatch":
        return "選択した曜日・時限とセルが一致しません。もう一度やり直してください。";
      case "invalid_academic_year":
        return "年度の指定が正しくありません。";
      case "invalid_semester":
      case "invalid_period":
      case "invalid_period_kind":
      case "invalid_day":
      case "missing_schedule":
      case "meetings_required":
        return "曜日・時限・学期の指定を確認してください。";
      case "title_required":
      case "instructor_required":
        return "授業名と担当教員名を入力してください。";
      case "invalid_school":
      case "invalid_campus":
        return "学部またはキャンパスの指定が正しくありません。";
      case "rate_limited":
        return "操作が多すぎます。時間をおいて再度お試しください。";
      case "csrf_failed":
        return "セキュリティチェックに失敗しました。ページを再読み込みしてから再度お試しください。";
      case "unauthorized":
      case "authentication_required":
        // 401 のみログイン案内。403 等を誤変換しない
        if (status != null && status !== 401) {
          return `授業の作成に失敗しました（${code}, HTTP ${status}）。`;
        }
        return "ログインが必要です。再度ログインしてからお試しください。";
      case "enroll_failed":
        return "授業は作成されましたが、時間割への追加に失敗しました。検索から追加してください。";
      case "save_failed":
        return "保存に失敗しました。時間をおいて再度お試しください。";
      default:
        if (code && status) {
          return `授業の作成に失敗しました（${code}, HTTP ${status}）。`;
        }
        return code
          ? `授業の作成に失敗しました（${code}）。`
          : "授業の作成に失敗しました。";
    }
  };

  const addMeeting = () => {
    setMeetings((prev) => {
      const next: MeetingDraft = {
        day_of_week: 0,
        period: 1,
        period_kind: "period",
      };
      // pick first free identity not already used
      for (let d = 0; d < 6; d += 1) {
        for (let p = 1; p <= 5; p += 1) {
          const candidate = {
            day_of_week: d,
            period: p,
            period_kind: "period",
          };
          if (
            !prev.some((m) => meetingIdentity(m) === meetingIdentity(candidate))
          ) {
            analytics.courseMeetingAddedDuringCreate();
            return [...prev, candidate];
          }
        }
      }
      analytics.courseMeetingAddedDuringCreate();
      return [...prev, next];
    });
  };

  const updateMeeting = (index: number, patch: Partial<MeetingDraft>) => {
    setMeetings((prev) =>
      prev.map((m, i) => {
        if (i !== index || m.locked) return m;
        const next = { ...m, ...patch };
        const dup = prev.some(
          (other, j) =>
            j !== index && meetingIdentity(other) === meetingIdentity(next)
        );
        if (dup) {
          window.alert("同じ曜日・時限は追加できません。");
          return m;
        }
        return next;
      })
    );
  };

  const removeMeeting = (index: number) => {
    setMeetings((prev) => {
      if (prev.length <= 1) return prev;
      if (prev[index]?.locked) return prev;
      return prev.filter((_, i) => i !== index);
    });
  };

  const localConflicts = (): string[] => {
    const msgs: string[] = [];
    for (const m of meetings) {
      const key = meetingToSlotKey(m);
      const entry = slots[key];
      if (!entry) continue;
      const occupied =
        Boolean(entry.offering_id) || Boolean((entry.name || "").trim());
      if (!occupied) continue;
      msgs.push(
        `${meetingLabel(m)}にはすでに「${entry.name || "別の授業"}」が登録されています`
      );
    }
    return msgs;
  };

  const submitCreate = async (force = false) => {
    if (!form.title.trim() || !form.instructor.trim()) {
      window.alert("授業名と担当教員名を入力してください。");
      return;
    }
    if (meetings.length === 0) {
      window.alert(createErrorMessage("meetings_required"));
      return;
    }
    const ids = meetings.map(meetingIdentity);
    if (new Set(ids).size !== ids.length) {
      window.alert("同じ曜日・時限は追加できません。");
      return;
    }
    const conflicts = localConflicts();
    if (conflicts.length) {
      window.alert(conflicts.join("\n"));
      return;
    }
    const primary = meetings[0];
    setBusy(true);
    try {
      const payload = {
        title: form.title.trim(),
        instructor: form.instructor.trim(),
        academic_year: Number(form.academic_year) || new Date().getFullYear(),
        semester: form.semester,
        day_of_week: primary.day_of_week,
        period: primary.period,
        period_kind: primary.period_kind,
        meetings: meetings.map((m) => ({
          day_of_week: m.day_of_week,
          period: m.period,
          period_kind: m.period_kind,
        })),
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
        setPendingCreate(payload);
        setMode("duplicates");
        return;
      }
      if (data.error === "slot_conflict") {
        const detail =
          data.conflicts
            ?.map((c) => {
              const label =
                meetings.find((m) => meetingToSlotKey(m) === c.slot_key) != null
                  ? meetingLabel(
                      meetings.find((m) => meetingToSlotKey(m) === c.slot_key)!
                    )
                  : c.slot_key;
              return `${label}にはすでに「${c.title}」が登録されています`;
            })
            .join("\n") || data.message || "";
        window.alert(detail || createErrorMessage("slot_conflict"));
        return;
      }
      if (!data.ok) {
        window.alert(createErrorMessage(data.error, data.status));
        if (data.created && data.offering) {
          setMode("search");
          setQuery(data.offering.title);
        }
        return;
      }
      if (!data.offering) {
        window.alert(createErrorMessage(data.error, data.status));
        return;
      }
      const slot: SlotPayload =
        data.slot ||
        ({
          slot_key: data.offering.slot_key,
          name: data.offering.title,
          room: data.offering.room || "",
          credits: data.offering.credits || "",
          memo: "",
          offering_id: data.offering.id,
        } satisfies SlotPayload);
      analytics.newCourseCreated({
        forced: force,
        meeting_count: data.meeting_count || meetings.length,
      });
      onAdded(slot, data.offering);
      showToast("新しい授業を追加しました");
      if (context.continuous) {
        setMode("search");
        setQuery("");
        setForm((f) => ({ ...f, title: "", instructor: "", room: "", credits: "" }));
        setMeetings([defaultMeeting(context)]);
      } else {
        window.setTimeout(() => onClose(), 350);
      }
    } catch (err) {
      const code = err instanceof Error ? err.message : undefined;
      const status =
        err && typeof err === "object" && "status" in err
          ? Number((err as { status?: number }).status)
          : undefined;
      window.alert(createErrorMessage(code, status));
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
              <div className="course-sheet__meetings">
                <p className="course-sheet__meetings-label">授業時間</p>
                <ul className="course-sheet__meeting-list">
                  {meetings.map((m, index) => (
                    <li key={`${meetingIdentity(m)}-${index}`}>
                      {m.locked ? (
                        <p className="course-sheet__locked">
                          {meetingLabel(m)}（セルから自動設定）
                        </p>
                      ) : (
                        <div className="course-sheet__meeting-row">
                          <select
                            aria-label="曜日"
                            value={m.day_of_week}
                            onChange={(e) =>
                              updateMeeting(index, {
                                day_of_week: Number(e.target.value),
                              })
                            }
                          >
                            {TIMETABLE_DAYS.map((d, i) => (
                              <option key={d} value={i}>
                                {d}
                              </option>
                            ))}
                          </select>
                          <select
                            aria-label="時限"
                            value={`${m.period_kind}:${m.period}`}
                            onChange={(e) => {
                              const [kind, num] = e.target.value.split(":");
                              updateMeeting(index, {
                                period_kind: kind,
                                period: Number(num),
                              });
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
                          {meetings.length > 1 ? (
                            <button
                              type="button"
                              className="course-sheet__meeting-remove"
                              onClick={() => removeMeeting(index)}
                            >
                              削除
                            </button>
                          ) : null}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  className="course-sheet__meeting-add"
                  onClick={addMeeting}
                >
                  ＋ 曜日時限を追加
                </button>
              </div>
            ) : (
              <div className="course-sheet__meetings">
                <p className="course-sheet__meetings-label">授業時間</p>
                <ul className="course-sheet__meeting-list">
                  {meetings.map((m, index) => (
                    <li key={`${meetingIdentity(m)}-${index}`}>
                      <div className="course-sheet__meeting-row">
                        <select
                          aria-label="曜日"
                          value={m.day_of_week}
                          onChange={(e) =>
                            updateMeeting(index, {
                              day_of_week: Number(e.target.value),
                            })
                          }
                        >
                          {TIMETABLE_DAYS.map((d, i) => (
                            <option key={d} value={i}>
                              {d}
                            </option>
                          ))}
                        </select>
                        <select
                          aria-label="時限"
                          value={`${m.period_kind}:${m.period}`}
                          onChange={(e) => {
                            const [kind, num] = e.target.value.split(":");
                            updateMeeting(index, {
                              period_kind: kind,
                              period: Number(num),
                            });
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
                        {meetings.length > 1 ? (
                          <button
                            type="button"
                            className="course-sheet__meeting-remove"
                            onClick={() => removeMeeting(index)}
                          >
                            削除
                          </button>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  className="course-sheet__meeting-add"
                  onClick={addMeeting}
                >
                  ＋ 曜日時限を追加
                </button>
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
