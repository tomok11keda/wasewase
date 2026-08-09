import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useSession } from "../lib/session";
import { spaLoginPath } from "../features/auth/api";
import {
  emptyEntry,
  fetchOwnSlots,
  fetchUserSlots,
  metaText,
  saveSlot,
  setTimetableVisibility,
  TIMETABLE_DAYS,
  TIMETABLE_OD_SLOTS,
  TIMETABLE_PERIODS,
  type SlotEntry,
  type SlotsMap,
} from "../features/timetable/api";
import { useSoftTabRefetch } from "../layouts/TabKeepAliveLayout";
import { TimetableCalendarView } from "../features/calendar/TimetableCalendarView";

type TimetableSectionId = "timetable" | "calendar";

const SECTION_TABS: Array<{ id: TimetableSectionId; label: string }> = [
  { id: "timetable", label: "時間割" },
  { id: "calendar", label: "カレンダー" },
  // Future: { id: "coupon", label: "クーポン" },
];

type ModalState = {
  slotKey: string;
  kind: "period" | "od";
  dayLabel: string;
  periodLabel: string;
  entry: SlotEntry;
};

function SlotButton({
  slotKey,
  kind,
  dayLabel,
  periodLabel,
  entry,
  readOnly,
  onOpen,
}: {
  slotKey: string;
  kind: "period" | "od";
  dayLabel: string;
  periodLabel: string;
  entry: SlotEntry;
  readOnly: boolean;
  onOpen: () => void;
}) {
  const filled = Boolean(entry.name);
  const meta = metaText(entry, kind);
  return (
    <button
      type="button"
      className={`timetable-slot ${filled ? "is-filled" : "is-empty"}`}
      data-timetable-slot
      data-slot-key={slotKey}
      data-slot-kind={kind}
      aria-label={`${dayLabel}曜 ${periodLabel}`}
      onClick={() => {
        if (readOnly) return;
        onOpen();
      }}
    >
      {filled ? (
        <>
          <p className="timetable-class__name">{entry.name}</p>
          {meta ? <p className="timetable-class__meta">{meta}</p> : null}
        </>
      ) : (
        <p className="timetable-slot__placeholder">
          {kind === "od" ? "OD" : "＋"}
        </p>
      )}
    </button>
  );
}

export function TimetablePage({
  overrideUserPk,
  embedded = false,
}: {
  overrideUserPk?: number;
  embedded?: boolean;
} = {}) {
  const { userPk: routeUserPk } = useParams();
  const navigate = useNavigate();
  const userPk = overrideUserPk != null ? String(overrideUserPk) : routeUserPk;
  const viewingOther = Boolean(userPk);
  const { me, loading: sessionLoading } = useSession();
  const [slots, setSlots] = useState<SlotsMap>({});
  const [isPublic, setIsPublic] = useState(false);
  const [readOnly, setReadOnly] = useState(false);
  const [title, setTitle] = useState("時間割");
  const [loading, setLoading] = useState(true);
  const [ready, setReady] = useState(false);
  const readyRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalState | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<SlotEntry>(emptyEntry());
  const [section, setSection] = useState<TimetableSectionId>("timetable");
  const showSectionTabs = !embedded && !viewingOther;

  const getEntry = useCallback(
    (slotKey: string): SlotEntry => {
      const entry = slots[slotKey];
      if (!entry) return emptyEntry();
      return {
        name: entry.name || "",
        room: entry.room || "",
        credits: entry.credits || "",
        memo: entry.memo || "",
      };
    },
    [slots]
  );

  const load = useCallback(
    async (mode: "initial" | "soft" = "initial") => {
      if (mode === "initial" && !readyRef.current) {
        setLoading(true);
      }
      setError(null);
      try {
        if (viewingOther && userPk) {
          const data = await fetchUserSlots(Number(userPk));
          if (data.is_own && !embedded) {
            navigate("/timetable", { replace: true });
            return;
          }
          if (data.is_own && embedded) {
            const own = await fetchOwnSlots();
            setSlots(own.slots || {});
            setIsPublic(Boolean(own.is_timetable_public));
            setReadOnly(false);
            setTitle("時間割");
            readyRef.current = true;
            setReady(true);
            return;
          }
          setSlots(data.slots || {});
          setIsPublic(true);
          setReadOnly(true);
          setTitle(`${data.owner.display_name}の時間割`);
          readyRef.current = true;
          setReady(true);
        } else if (me?.authenticated) {
          const data = await fetchOwnSlots();
          setSlots(data.slots || {});
          setIsPublic(Boolean(data.is_timetable_public));
          setReadOnly(false);
          setTitle("時間割");
          readyRef.current = true;
          setReady(true);
        } else {
          setSlots({});
          setIsPublic(false);
          setReadOnly(false);
          setTitle("時間割");
          readyRef.current = true;
          setReady(true);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "load_failed");
      } finally {
        setLoading(false);
      }
    },
    [viewingOther, userPk, me?.authenticated, navigate, embedded]
  );

  useEffect(() => {
    if (sessionLoading) return;
    void load(readyRef.current ? "soft" : "initial");
  }, [sessionLoading, load]);

  useSoftTabRefetch("timetable", () => {
    if (!viewingOther && !embedded) {
      void load("soft");
    }
  });

  // Clean up modal body class on leave / unmount
  useEffect(() => {
    return () => {
      document.body.classList.remove("timetable-modal-open");
    };
  }, []);

  useEffect(() => {
    if (!modal) {
      document.body.classList.remove("timetable-modal-open");
      return;
    }
    document.body.classList.add("timetable-modal-open");
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setModal(null);
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("timetable-modal-open");
    };
  }, [modal]);

  const openSlot = (
    slotKey: string,
    kind: "period" | "od",
    dayLabel: string,
    periodLabel: string
  ) => {
    if (readOnly) return;
    const entry = getEntry(slotKey);
    setDraft({
      ...entry,
      room: kind === "od" ? "" : entry.room,
    });
    setModal({ slotKey, kind, dayLabel, periodLabel, entry });
  };

  const closeModal = () => setModal(null);

  const applyLocal = (slotKey: string, entry: SlotEntry) => {
    const normalized = {
      name: (entry.name || "").trim(),
      room: (entry.room || "").trim(),
      credits: (entry.credits || "").trim(),
      memo: (entry.memo || "").trim(),
    };
    setSlots((prev) => {
      const next = { ...prev };
      if (
        !normalized.name &&
        !normalized.room &&
        !normalized.credits &&
        !normalized.memo
      ) {
        delete next[slotKey];
      } else {
        next[slotKey] = normalized;
      }
      return next;
    });
  };

  const persistSlot = async (slotKey: string, entry: SlotEntry) => {
    if (!me?.authenticated) {
      applyLocal(slotKey, entry);
      return entry;
    }
    const result = await saveSlot(slotKey, entry);
    applyLocal(slotKey, result.entry);
    return result.entry;
  };

  const onSave = async (e: FormEvent) => {
    e.preventDefault();
    if (!modal) return;
    setBusy(true);
    try {
      const payload = {
        name: draft.name,
        room: modal.kind === "od" ? "" : draft.room,
        credits: draft.credits,
        memo: draft.memo,
      };
      await persistSlot(modal.slotKey, payload);
      closeModal();
    } catch {
      window.alert(
        "時間割の保存に失敗しました。通信環境を確認して再度お試しください。"
      );
    } finally {
      setBusy(false);
    }
  };

  const onClear = async () => {
    if (!modal) return;
    setBusy(true);
    try {
      await persistSlot(modal.slotKey, emptyEntry());
      closeModal();
    } catch {
      window.alert(
        "時間割の削除に失敗しました。通信環境を確認して再度お試しください。"
      );
    } finally {
      setBusy(false);
    }
  };

  const onVisibilityChange = async (next: boolean) => {
    const previous = isPublic;
    setIsPublic(next);
    try {
      const result = await setTimetableVisibility(next);
      setIsPublic(Boolean(result.is_timetable_public));
    } catch {
      setIsPublic(previous);
      window.alert(
        "公開設定の更新に失敗しました。時間をおいて再度お試しください。"
      );
    }
  };

  const canEditVisibility = Boolean(me?.authenticated) && !viewingOther;

  return (
    <div
      className={`timetable-page${readOnly ? " is-read-only" : ""}`}
      data-spa-page={embedded ? undefined : "時間割"}
    >
      <main className="main-inner main-inner--timetable">
        {!embedded ? (
          <div className="page-title-row">
            <h1 className="page-title">{title}</h1>
            {canEditVisibility ? (
              <div className="timetable-visibility" data-timetable-visibility>
                <span
                  className={`timetable-visibility__badge${
                    isPublic ? " is-public" : " is-private"
                  }`}
                >
                  {isPublic ? "公開中" : "非公開"}
                </span>
                <label
                  className="timetable-visibility__switch"
                  title="時間割の公開設定"
                >
                  <span className="visually-hidden">時間割を公開する</span>
                  <input
                    type="checkbox"
                    checked={isPublic}
                    onChange={(e) => void onVisibilityChange(e.target.checked)}
                  />
                  <span
                    className="timetable-visibility__slider"
                    aria-hidden="true"
                  />
                </label>
              </div>
            ) : viewingOther ? (
              <span className="timetable-visibility__badge is-public">公開中</span>
            ) : null}
          </div>
        ) : null}

        {showSectionTabs ? (
          <nav className="tt-section-tabs" aria-label="時間割の表示切替">
            {SECTION_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`tt-section-tabs__btn${
                  section === tab.id ? " is-active" : ""
                }`}
                aria-pressed={section === tab.id}
                onClick={() => setSection(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        ) : null}

        {(loading || sessionLoading) && !ready ? (
          <p className="timetable-note">読み込み中…</p>
        ) : error && !ready ? (
          <p className="timetable-note">
            読み込みに失敗しました（{error}）
            {error === "private" ? "。この時間割は非公開です。" : ""}
          </p>
        ) : showSectionTabs && section === "calendar" ? (
          <TimetableCalendarView
            slots={slots}
            authenticated={Boolean(me?.authenticated)}
          />
        ) : (
          <section className="timetable-board" aria-label="週間時間割">
            <div className="timetable-scroll">
              <div className="timetable-grid" data-timetable-grid>
                <div className="timetable-corner" aria-hidden="true" />
                {TIMETABLE_DAYS.map((day) => (
                  <div className="timetable-day" role="columnheader" key={day}>
                    {day}
                  </div>
                ))}

                {TIMETABLE_PERIODS.map((period) => (
                  <PeriodRow
                    key={`p${period.number}`}
                    period={period}
                    kind="period"
                    getEntry={getEntry}
                    readOnly={readOnly}
                    onOpen={openSlot}
                  />
                ))}

                {TIMETABLE_OD_SLOTS.map((od) => (
                  <PeriodRow
                    key={`od${od.number}`}
                    period={od}
                    kind="od"
                    getEntry={getEntry}
                    readOnly={readOnly}
                    onOpen={openSlot}
                  />
                ))}
              </div>
            </div>
          </section>
        )}

        {showSectionTabs && section === "calendar" ? null : readOnly &&
          viewingOther ? (
          <p className="timetable-note">公開中の時間割です（閲覧のみ）。</p>
        ) : (
          <p className="timetable-note">
            セルをタップして授業名・単位・進捗メモを登録できます。右上のトグルで公開／非公開を切り替えられます。
            {!me?.authenticated ? (
              <>
                {" "}
                <Link to={spaLoginPath("/app/timetable")}>
                  ログイン
                </Link>
                すると保存できます。
              </>
            ) : null}
          </p>
        )}
      </main>

      {modal ? (
        <div
          className="compose-modal"
          id="timetable-slot-modal"
          aria-hidden="false"
        >
          <div
            className="compose-modal__backdrop"
            data-timetable-modal-close
            onClick={closeModal}
          />
          <div
            className="compose-modal__panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="timetable-slot-modal-title"
          >
            <header className="compose-modal__header">
              <h2 id="timetable-slot-modal-title">
                {modal.kind === "od" ? "オンデマンド授業" : "授業詳細"}
              </h2>
              <button
                type="button"
                className="compose-modal__close"
                aria-label="閉じる"
                onClick={closeModal}
              >
                ×
              </button>
            </header>
            <p className="timetable-modal-hint">
              {modal.dayLabel
                ? `${modal.dayLabel}曜・${modal.periodLabel}`
                : modal.periodLabel}
            </p>
            <form onSubmit={onSave} noValidate>
              <div className="compose-image-field">
                <label htmlFor="timetable-slot-name">授業名</label>
                <input
                  id="timetable-slot-name"
                  type="text"
                  maxLength={80}
                  placeholder="例：マクロ経済学"
                  autoComplete="off"
                  value={draft.name}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, name: e.target.value }))
                  }
                  autoFocus
                />
              </div>
              <div
                className="compose-image-field room-field"
                hidden={modal.kind === "od"}
              >
                <label htmlFor="timetable-slot-room">教室</label>
                <input
                  id="timetable-slot-room"
                  type="text"
                  maxLength={40}
                  placeholder="例：11-503"
                  autoComplete="off"
                  value={draft.room}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, room: e.target.value }))
                  }
                />
              </div>
              <div className="compose-image-field">
                <label htmlFor="timetable-slot-credits">単位数</label>
                <input
                  id="timetable-slot-credits"
                  type="text"
                  inputMode="decimal"
                  maxLength={8}
                  placeholder="例：2"
                  autoComplete="off"
                  value={draft.credits}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, credits: e.target.value }))
                  }
                />
              </div>
              <div className="compose-image-field">
                <label htmlFor="timetable-slot-memo">進捗・課題メモ</label>
                <textarea
                  id="timetable-slot-memo"
                  maxLength={500}
                  placeholder="課題の締切や進捗をメモ"
                  value={draft.memo}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, memo: e.target.value }))
                  }
                />
              </div>
              <div className="timetable-modal-actions">
                <button
                  type="button"
                  className="btn-timetable-clear"
                  onClick={() => void onClear()}
                  disabled={busy}
                >
                  クリア
                </button>
                <button type="submit" className="btn-compose" disabled={busy}>
                  保存
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function PeriodRow({
  period,
  kind,
  getEntry,
  readOnly,
  onOpen,
}: {
  period: { number: number; label: string; time: string };
  kind: "period" | "od";
  getEntry: (slotKey: string) => SlotEntry;
  readOnly: boolean;
  onOpen: (
    slotKey: string,
    kind: "period" | "od",
    dayLabel: string,
    periodLabel: string
  ) => void;
}) {
  const prefix = kind === "od" ? "od" : "p";
  return (
    <>
      <div
        className={`timetable-period${kind === "od" ? " is-od" : ""}`}
        role="rowheader"
      >
        <span className="timetable-period__label">{period.label}</span>
        <span className="timetable-period__time">{period.time}</span>
      </div>
      {TIMETABLE_DAYS.map((dayLabel, dayIndex) => {
        const slotKey = `${prefix}${period.number}-d${dayIndex}`;
        return (
          <div
            className={`timetable-cell${kind === "od" ? " is-od" : ""}`}
            data-slot-wrap={slotKey}
            key={slotKey}
          >
            <SlotButton
              slotKey={slotKey}
              kind={kind}
              dayLabel={dayLabel}
              periodLabel={period.label}
              entry={getEntry(slotKey)}
              readOnly={readOnly}
              onOpen={() => onOpen(slotKey, kind, dayLabel, period.label)}
            />
          </div>
        );
      })}
    </>
  );
}
