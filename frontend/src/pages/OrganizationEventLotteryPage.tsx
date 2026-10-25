import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ListRowSkeleton } from "../components/skeleton";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import {
  defaultLotteryEligibleIds,
  EXCLUSION_NOTE_MAX,
  eventCapacityLabel,
  formatTokyoDateTime,
  lotteryResultLabel,
  organizationEventErrorMessage,
  organizationEventPath,
  validateLotterySetup,
  type OrganizationEvent,
  type OrganizationEventLottery,
  type OrganizationEventLotteryEntry,
  type OrganizationEventRegistrant,
} from "../features/orgs/orgEvents";
import {
  fetchAllOrganizationEventRegistrations,
  fetchOrganizationEvent,
  fetchOrganizationEventLottery,
  runOrganizationEventLottery,
  shareOrganizationEventLottery,
} from "../features/orgs/orgEventsApi";
import { isBrowsePreview, useSession } from "../lib/session";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

function recruitingChatPathSafeLocal(slug: string): string {
  return `/organizations/${slug}/recruiting-chat`;
}

function errorCode(err: unknown): string {
  return err instanceof OrganizationRequestError ? err.code : "load_failed";
}

function PersonRow({
  entry,
  note,
}: {
  entry: OrganizationEventLotteryEntry | OrganizationEventRegistrant;
  note?: string;
}) {
  const user = entry.user;
  return (
    <li className="org-event-person">
      <span className="org-event-person__avatar" aria-hidden="true">
        {user.avatar_url ? (
          <img src={user.avatar_url} alt="" />
        ) : (
          user.initial || "?"
        )}
      </span>
      <span className="org-event-person__text">
        <strong>{user.display_name}</strong>
        {user.username ? <span>@{user.username}</span> : null}
        {note ? <em>{note}</em> : null}
      </span>
    </li>
  );
}

function ResultLists({ lottery }: { lottery: OrganizationEventLottery }) {
  return (
    <div className="org-event-lottery-lists">
      <section>
        <h2>当選（{lottery.selected.length}）</h2>
        {lottery.selected.length === 0 ? (
          <p className="org-recruiting-card__lead">該当者はいません。</p>
        ) : (
          <ul className="org-event-person-list">
            {lottery.selected.map((entry) => (
              <PersonRow key={entry.id} entry={entry} />
            ))}
          </ul>
        )}
      </section>
      <section>
        <h2>落選（{lottery.not_selected.length}）</h2>
        {lottery.not_selected.length === 0 ? (
          <p className="org-recruiting-card__lead">該当者はいません。</p>
        ) : (
          <ul className="org-event-person-list">
            {lottery.not_selected.map((entry) => (
              <PersonRow key={entry.id} entry={entry} />
            ))}
          </ul>
        )}
      </section>
      <section>
        <h2>対象外（{lottery.excluded.length}）</h2>
        {lottery.excluded.length === 0 ? (
          <p className="org-recruiting-card__lead">該当者はいません。</p>
        ) : (
          <ul className="org-event-person-list">
            {lottery.excluded.map((entry) => (
              <PersonRow
                key={entry.id}
                entry={entry}
                note={entry.exclusion_note || "備考なし"}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export function OrganizationEventLotteryPage() {
  const { slug, eventId: eventIdRaw } = useParams();
  const eventId = Number(eventIdRaw);
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const busyRef = useRef(false);
  const [event, setEvent] = useState<OrganizationEvent | null>(null);
  const [lottery, setLottery] = useState<OrganizationEventLottery | null>(null);
  const [registrations, setRegistrations] = useState<OrganizationEventRegistrant[]>(
    []
  );
  const [eligibleIds, setEligibleIds] = useState<number[]>([]);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [winnerCount, setWinnerCount] = useState("");
  const [step, setStep] = useState<"select" | "confirm">("select");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setEvent(null);
    setLottery(null);
    setRegistrations([]);
    setEligibleIds([]);
    setNotes({});
    setWinnerCount("");
    setStep("select");
    setError(null);
    setActionError(null);
    setFieldErrors({});
    setLoading(true);
  }, [slug, eventId, sessionUserId]);

  const load = useCallback(async () => {
    if (!slug || !Number.isInteger(eventId) || eventId <= 0) {
      setError("not_found");
      setLoading(false);
      return;
    }
    const gen = nextRequestId(fetchGen);
    const startedUserId = userIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const current = await fetchOrganizationEvent(slug, eventId);
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setEvent(current);
      if (current.has_lottery) {
        try {
          const payload = await fetchOrganizationEventLottery(slug, eventId);
          if (!isLatestRequest(fetchGen, gen)) return;
          if (!isSameUserScope(startedUserId, userIdRef.current)) return;
          setEvent(payload.event);
          setLottery(payload.lottery);
        } catch (err) {
          if (errorCode(err) !== "forbidden") throw err;
        }
      } else if (current.can_run_lottery) {
        const payload = await fetchAllOrganizationEventRegistrations(slug, eventId);
        if (!isLatestRequest(fetchGen, gen)) return;
        if (!isSameUserScope(startedUserId, userIdRef.current)) return;
        setEvent(payload.event);
        setRegistrations(payload.registrations);
        const ids = defaultLotteryEligibleIds(payload.registrations);
        setEligibleIds(ids);
        setWinnerCount(ids.length ? String(ids.length) : "0");
      } else {
        setError("forbidden");
      }
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setError(errorCode(err));
    } finally {
      if (isLatestRequest(fetchGen, gen)) setLoading(false);
    }
  }, [slug, eventId]);

  useEffect(() => {
    if (sessionLoading) return;
    void load();
  }, [load, sessionLoading]);

  const eligibleSet = useMemo(() => new Set(eligibleIds), [eligibleIds]);
  const excluded = useMemo(
    () => registrations.filter((row) => !eligibleSet.has(row.user.id)),
    [registrations, eligibleSet]
  );

  if (!slug) return <Navigate to="/" replace />;
  const loginNext = `/app/organizations/${slug}/events/${eventId}/lottery`;
  if (browsePreview || (!sessionLoading && !me?.authenticated)) {
    return (
      <div className="page-detail" data-spa-page="イベント抽選">
        <div className="main-inner">
          <p>抽選の確認にはログインが必要です。</p>
          <Link className="btn btn-primary" to={spaLoginPath(loginNext)}>
            ログイン
          </Link>
        </div>
      </div>
    );
  }

  const toggleEligible = (userId: number, checked: boolean) => {
    setEligibleIds((current) => {
      if (checked) return current.includes(userId) ? current : [...current, userId];
      return current.filter((id) => id !== userId);
    });
    if (checked) {
      setNotes((current) => {
        const next = { ...current };
        delete next[userId];
        return next;
      });
    }
  };

  const goConfirm = () => {
    const errors = validateLotterySetup({
      winnerCount,
      eligibleCount: eligibleIds.length,
      notes,
    });
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    setStep("confirm");
    setActionError(null);
  };

  const runLottery = async () => {
    if (!slug || busyRef.current) return;
    const errors = validateLotterySetup({
      winnerCount,
      eligibleCount: eligibleIds.length,
      notes,
    });
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    busyRef.current = true;
    setBusy(true);
    setActionError(null);
    try {
      const payload = await runOrganizationEventLottery(slug, eventId, {
        winner_count: Number(winnerCount.trim()),
        applicant_ids: registrations.map((row) => row.user.id),
        excluded: excluded.map((row) => ({
          user_id: row.user.id,
          note: (notes[row.user.id] || "").slice(0, EXCLUSION_NOTE_MAX),
        })),
      });
      setEvent(payload.event);
      setLottery(payload.lottery);
      setStep("select");
    } catch (err) {
      const code = errorCode(err);
      if (code === "registrants_changed") {
        setStep("select");
        await load();
      }
      setActionError(
        err instanceof OrganizationRequestError
          ? err.message
          : "抽選を実行できませんでした。"
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const shareLottery = async () => {
    if (!slug || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setActionError(null);
    try {
      const payload = await shareOrganizationEventLottery(slug, eventId);
      setEvent(payload.event);
      setLottery(payload.lottery);
    } catch (err) {
      setActionError(
        err instanceof OrganizationRequestError
          ? err.message
          : "共有できませんでした。"
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const view =
    loading && !event
      ? "loading"
      : event
        ? "ready"
        : error === "not_found" || error === "forbidden" || error === "no_lottery"
          ? "missing"
          : error
            ? "error"
            : "missing";

  return (
    <div className="page-detail" data-spa-page="イベント抽選">
      <div className="main-inner">
        {view === "loading" ? (
          <ListRowSkeleton rows={6} />
        ) : view === "missing" ? (
          <p>抽選画面を表示できません。</p>
        ) : view === "error" ? (
          <>
            <p role="alert">
              {organizationEventErrorMessage(error || undefined, "通信に失敗しました。")}
            </p>
            <button type="button" className="btn btn-secondary" onClick={() => void load()}>
              再試行
            </button>
          </>
        ) : event && lottery ? (
          <section className="org-recruiting-card" aria-label="抽選結果">
            <p className="org-event-kicker">{event.organization_name}</p>
            <h1 className="org-recruiting-card__title">{event.title}</h1>
            <ul className="org-recruiting-card__meta">
              <li>抽選 {formatTokyoDateTime(lottery.executed_at)}</li>
              <li>申込 {lottery.applicant_count}人</li>
              <li>対象 {lottery.eligible_count}人</li>
              <li>当選 {lottery.winner_count}人</li>
              <li>落選 {lottery.not_selected_count}人</li>
              <li>対象外 {lottery.excluded_count}人</li>
            </ul>
            {event.viewer_lottery_result ? (
              <p className="org-recruiting-card__pending">
                あなたの結果：{lotteryResultLabel(event.viewer_lottery_result)}
              </p>
            ) : null}
            {actionError ? (
              <p className="org-edit-error" role="alert">
                {actionError}
              </p>
            ) : null}
            {lottery.can_manage ? (
              <p className="org-recruiting-card__actions">
                {lottery.can_share ? (
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={busy}
                    onClick={() => void shareLottery()}
                  >
                    {busy ? "送信中…" : "新歓チャットに結果を共有"}
                  </button>
                ) : lottery.shared ? (
                  <span>新歓チャットへ共有済みです。</span>
                ) : null}
                {lottery.shared ? (
                  <Link className="btn btn-secondary" to={recruitingChatPathSafeLocal(slug)}>
                    新歓チャットを開く
                  </Link>
                ) : null}
              </p>
            ) : null}
            {lottery.lists_visible ? (
              <ResultLists lottery={lottery} />
            ) : lottery.viewer_entry ? (
              <p className="org-recruiting-card__lead">
                詳細一覧は新歓チャットの正式メンバーが確認できます。
              </p>
            ) : (
              <p className="org-recruiting-card__lead">
                抽選は確定しています。詳細一覧は新歓チャットのメンバーが確認できます。
              </p>
            )}
            <p>
              <Link to={organizationEventPath(slug, event.id)}>イベント詳細へ</Link>
            </p>
          </section>
        ) : event && event.has_lottery && !event.can_view_lottery ? (
          <section className="org-recruiting-card" aria-label="抽選結果">
            <h1 className="org-recruiting-card__title">{event.title}</h1>
            <p className="org-recruiting-card__lead">
              {event.viewer_lottery_result
                ? `あなたの結果：${lotteryResultLabel(event.viewer_lottery_result)}`
                : "抽選は確定しています。詳細一覧は新歓チャットのメンバーが確認できます。"}
            </p>
            <p>
              <Link to={organizationEventPath(slug, event.id)}>イベント詳細へ</Link>
            </p>
          </section>
        ) : event && event.can_run_lottery ? (
          <section className="org-recruiting-card" aria-label="抽選する">
            <p className="org-event-kicker">{event.organization_name}</p>
            <h1 className="org-recruiting-card__title">{event.title}</h1>
            <p className="org-recruiting-card__lead">{eventCapacityLabel(event)}</p>
            {actionError ? (
              <p className="org-edit-error" role="alert">
                {actionError}
              </p>
            ) : null}
            {step === "select" ? (
              <>
                <p className="org-event-privacy">
                  初期状態では有効な申込者全員が抽選対象です。チェックを外すと対象外になります。備考は任意ですが、公開される可能性があります。健康情報や連絡先など機微な内容は書かないでください。
                </p>
                <ul className="org-event-person-list">
                  {registrations.map((row) => {
                    const checked = eligibleSet.has(row.user.id);
                    return (
                      <li key={row.id} className="org-event-person org-event-person--select">
                        <label className="org-event-check">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) => toggleEligible(row.user.id, e.target.checked)}
                          />
                          <span className="org-event-person__avatar" aria-hidden="true">
                            {row.user.avatar_url ? (
                              <img src={row.user.avatar_url} alt="" />
                            ) : (
                              row.user.initial
                            )}
                          </span>
                          <span className="org-event-person__text">
                            <strong>{row.user.display_name}</strong>
                            {row.user.username ? <span>@{row.user.username}</span> : null}
                          </span>
                        </label>
                        {!checked ? (
                          <label className="org-event-note">
                            除外備考（任意・最大{EXCLUSION_NOTE_MAX}文字）
                            <input
                              value={notes[row.user.id] || ""}
                              maxLength={EXCLUSION_NOTE_MAX}
                              onChange={(e) =>
                                setNotes((current) => ({
                                  ...current,
                                  [row.user.id]: e.target.value,
                                }))
                              }
                            />
                          </label>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
                <label>
                  当選人数
                  <input
                    inputMode="numeric"
                    value={winnerCount}
                    onChange={(e) => setWinnerCount(e.target.value)}
                  />
                  {fieldErrors.winner_count ? (
                    <span className="org-edit-error">{fieldErrors.winner_count}</span>
                  ) : null}
                </label>
                {fieldErrors.exclusion_note ? (
                  <p className="org-edit-error">{fieldErrors.exclusion_note}</p>
                ) : null}
                <p className="org-recruiting-card__lead">
                  申込 {registrations.length}人 / 対象 {eligibleIds.length}人 / 除外{" "}
                  {excluded.length}人
                </p>
                <p className="org-recruiting-card__actions">
                  <button type="button" className="btn btn-primary" onClick={goConfirm}>
                    確認画面へ
                  </button>
                </p>
              </>
            ) : (
              <>
                <ul className="org-recruiting-card__meta">
                  <li>有効申込者 {registrations.length}人</li>
                  <li>抽選対象 {eligibleIds.length}人</li>
                  <li>除外 {excluded.length}人</li>
                  <li>当選予定 {winnerCount}人</li>
                </ul>
                {excluded.length ? (
                  <section>
                    <h2>除外者と備考</h2>
                    <ul className="org-event-person-list">
                      {excluded.map((row) => (
                        <PersonRow
                          key={row.id}
                          entry={row}
                          note={notes[row.user.id] || "備考なし"}
                        />
                      ))}
                    </ul>
                  </section>
                ) : (
                  <p className="org-recruiting-card__lead">除外者はいません。</p>
                )}
                <p className="org-event-privacy">
                  この条件で抽選を確定しますか？確定後は結果や除外者の備考を変更できません。除外備考は新歓チャットの正式メンバーに公開されることがあります。健康情報や連絡先など機微な内容は書かないでください。
                </p>
                <p className="org-recruiting-card__actions">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={busy}
                    onClick={() => setStep("select")}
                  >
                    戻る
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={busy}
                    onClick={() => void runLottery()}
                  >
                    {busy ? "抽選中…" : "抽選を確定する"}
                  </button>
                </p>
              </>
            )}
            <p>
              <Link to={organizationEventPath(slug, event.id)}>イベント詳細へ</Link>
            </p>
          </section>
        ) : (
          <p>抽選画面を表示できません。</p>
        )}
      </div>
    </div>
  );
}
