import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import { RecruitingManageNav } from "../features/orgs/RecruitingManageNav";
import {
  MAX_RECRUITING_INVITEES,
  RECRUITING_INVITE_QUERY_MIN,
  canShowRecruitingManageNav,
  formatRecruitingDate,
  recruitingInviteSkipLabel,
  type RecruitingInvitation,
  type RecruitingInviteCandidate,
} from "../features/orgs/recruitingChat";
import {
  cancelRecruitingInvite,
  fetchRecruitingChat,
  fetchRecruitingInvites,
  searchRecruitingInviteCandidates,
  sendRecruitingInvites,
} from "../features/orgs/recruitingChatApi";
import { isBrowsePreview, useSession } from "../lib/session";
import { PeopleListSkeleton } from "../components/skeleton";
import {
  isLatestRequest,
  isSameUserScope,
  nextRequestId,
} from "../lib/userScopedResult";

function errorText(err: unknown, fallback: string): string {
  if (err instanceof OrganizationRequestError) return err.message;
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function OrganizationRecruitingChatInvitesPage() {
  const { slug } = useParams();
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const searchGen = useRef(0);
  const slugRef = useRef(slug);
  slugRef.current = slug;
  const [canManage, setCanManage] = useState(false);
  const [canInvite, setCanInvite] = useState(false);
  const [pendingCount, setPendingCount] = useState<number | undefined>(undefined);
  const [invites, setInvites] = useState<RecruitingInvitation[]>([]);
  const [candidates, setCandidates] = useState<RecruitingInviteCandidate[]>([]);
  const [selected, setSelected] = useState<Map<number, RecruitingInviteCandidate>>(
    () => new Map()
  );
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const sendingRef = useRef(false);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    nextRequestId(searchGen);
    setInvites([]);
    setCandidates([]);
    setSelected(new Map());
    setQuery("");
    setCanManage(false);
    setCanInvite(false);
    setPendingCount(undefined);
    setError(null);
    setFeedback(null);
    setLoading(true);
  }, [slug, sessionUserId]);

  const load = useCallback(async () => {
    if (!slug) return;
    const gen = nextRequestId(fetchGen);
    const startedUserId = userIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const envelope = await fetchRecruitingChat(slug);
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      const manage =
        envelope.can_manage || Boolean(envelope.recruiting_chat?.can_manage);
      setCanManage(manage);
      setCanInvite(Boolean(envelope.recruiting_chat?.can_invite));
      setPendingCount(envelope.recruiting_chat?.pending_count);
      if (!manage) {
        setError("forbidden");
        setInvites([]);
        return;
      }
      const rows = await fetchRecruitingInvites(slug);
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setInvites(rows);
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setInvites([]);
      setCanManage(false);
      setError(
        err instanceof OrganizationRequestError ? err.code : "load_failed"
      );
    } finally {
      if (isLatestRequest(fetchGen, gen)) setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    if (sessionLoading || browsePreview) return;
    void load();
  }, [sessionLoading, browsePreview, load, sessionUserId]);

  useEffect(() => {
    if (!slug || !canManage) return;
    const trimmed = query.trim().replace(/^@/, "");
    const gen = nextRequestId(searchGen);
    if (trimmed.length < RECRUITING_INVITE_QUERY_MIN) {
      setCandidates([]);
      setSearching(false);
      return;
    }
    const handle = window.setTimeout(() => {
      setSearching(true);
      void searchRecruitingInviteCandidates(slug, trimmed)
        .then((rows) => {
          if (!isLatestRequest(searchGen, gen)) return;
          if (slugRef.current !== slug) return;
          setCandidates(rows);
        })
        .catch((err) => {
          if (!isLatestRequest(searchGen, gen)) return;
          setCandidates([]);
          setError(errorText(err, "学生を検索できませんでした。"));
        })
        .finally(() => {
          if (isLatestRequest(searchGen, gen)) setSearching(false);
        });
    }, 250);
    return () => window.clearTimeout(handle);
  }, [query, slug, canManage]);

  if (!slug) return <Navigate to="/" replace />;
  const loginNext = `/app/organizations/${slug}/recruiting-chat/invites`;

  if (browsePreview || (!sessionLoading && !me?.authenticated)) {
    return (
      <div className="org-edit-page" data-spa-page="学生を招待">
        <div className="main-inner">
          <p>学生の招待にはログインが必要です。</p>
          <Link className="btn btn-primary" to={spaLoginPath(loginNext)}>
            ログイン
          </Link>
        </div>
      </div>
    );
  }

  const toggle = (row: RecruitingInviteCandidate) => {
    if (row.id == null) return;
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(row.id as number)) {
        next.delete(row.id as number);
        return next;
      }
      if (next.size >= MAX_RECRUITING_INVITEES) return prev;
      next.set(row.id as number, row);
      return next;
    });
  };

  const onSend = async () => {
    if (sendingRef.current || selected.size === 0) return;
    const startedSlug = slug;
    sendingRef.current = true;
    setSending(true);
    setError(null);
    setFeedback(null);
    try {
      const result = await sendRecruitingInvites(startedSlug, [...selected.keys()]);
      if (slugRef.current !== startedSlug) return;
      const skipText = result.skipped
        .map((row) => recruitingInviteSkipLabel(row.reason))
        .filter((value, index, all) => all.indexOf(value) === index);
      if (result.invited_count > 0 && result.skipped.length === 0) {
        setFeedback(`${result.invited_count}人を招待しました。`);
      } else if (result.invited_count > 0) {
        setFeedback(
          `${result.invited_count}人を招待しました。一部はスキップしました（${skipText.join("、")}）。`
        );
      } else {
        setFeedback(`招待できませんでした（${skipText.join("、") || "対象なし"}）。`);
      }
      setSelected(new Map());
      const rows = await fetchRecruitingInvites(startedSlug);
      if (slugRef.current !== startedSlug) return;
      setInvites(rows);
    } catch (err) {
      if (slugRef.current !== startedSlug) return;
      setError(errorText(err, "招待を送信できませんでした。"));
    } finally {
      if (slugRef.current === startedSlug) {
        sendingRef.current = false;
        setSending(false);
      } else {
        sendingRef.current = false;
      }
    }
  };

  const onCancel = async (invitation: RecruitingInvitation) => {
    if (busyId != null) return;
    if (!window.confirm("この招待を取り消しますか？")) return;
    const startedSlug = slug;
    setBusyId(invitation.id);
    setError(null);
    try {
      await cancelRecruitingInvite(startedSlug, invitation.id);
      if (slugRef.current !== startedSlug) return;
      setInvites((prev) => prev.filter((row) => row.id !== invitation.id));
    } catch (err) {
      if (slugRef.current !== startedSlug) return;
      setError(errorText(err, "招待を取り消せませんでした。"));
    } finally {
      if (slugRef.current === startedSlug) setBusyId(null);
    }
  };

  return (
    <div
      className="org-edit-page org-recruiting-manage-page"
      data-spa-page="学生を招待"
    >
      <div className="main-inner">
        <p className="form-lead">
          団体のowner/adminだけが学生を団体チャットへ招待できます。承諾されるまでメンバーにはなりません。
        </p>
        {canShowRecruitingManageNav({
          hydrated: !loading && !sessionLoading,
          canManage,
        }) ? (
          <RecruitingManageNav slug={slug} pendingCount={pendingCount} />
        ) : null}
        {loading || sessionLoading ? (
          <PeopleListSkeleton />
        ) : error === "forbidden" || error === "not_found" ? (
          <p>学生を招待する権限がありません。</p>
        ) : (
          <>
            {error ? (
              <p className="org-edit-error" role="alert">
                {error}
              </p>
            ) : null}
            {feedback ? (
              <p className="org-recruiting-invite-feedback" role="status">
                {feedback}
              </p>
            ) : null}

            {canInvite ? (
              <section className="org-recruiting-invite-search" aria-label="学生検索">
                <label htmlFor="recruiting-invite-q">学生を検索</label>
                <input
                  id="recruiting-invite-q"
                  className="dm-search-input"
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="名前またはユーザー名"
                  autoComplete="off"
                />
                <p className="org-recruiting-count">
                  選択中 {selected.size}/{MAX_RECRUITING_INVITEES}人
                </p>
                {selected.size > 0 ? (
                  <ul className="org-recruiting-invite-selected">
                    {[...selected.values()].map((row) => (
                      <li key={row.id}>
                        <button type="button" onClick={() => toggle(row)}>
                          {row.display_name || row.username}
                          <span aria-hidden="true"> ×</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
                {searching ? <PeopleListSkeleton rows={3} /> : null}
                {!searching &&
                query.trim().replace(/^@/, "").length >= RECRUITING_INVITE_QUERY_MIN &&
                candidates.length === 0 ? (
                  <p className="org-profile-empty">該当する学生はいません。</p>
                ) : null}
                {candidates.length > 0 ? (
                  <ul className="org-recruiting-people">
                    {candidates.map((row) => {
                      const name = row.display_name || row.username || "ユーザー";
                      const checked = row.id != null && selected.has(row.id);
                      return (
                        <li key={row.id} className="org-recruiting-person">
                          <label className="org-recruiting-person__identity">
                            {row.avatar_url ? (
                              <img src={row.avatar_url} alt="" />
                            ) : (
                              <span aria-hidden="true">{row.initial || name.slice(0, 1)}</span>
                            )}
                            <div>
                              <strong>{name}</strong>
                              <p>@{row.username || "不明"}</p>
                            </div>
                            <input
                              type="checkbox"
                              checked={checked}
                              disabled={
                                !checked && selected.size >= MAX_RECRUITING_INVITEES
                              }
                              onChange={() => toggle(row)}
                            />
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
                <div className="org-recruiting-invite-send">
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={sending || selected.size === 0}
                    onClick={() => void onSend()}
                  >
                    {sending ? "送信中…" : "招待を送る"}
                  </button>
                </div>
              </section>
            ) : (
              <p className="org-recruiting-card__closed" role="status">
                募集停止中のため、新しい招待は送れません。
              </p>
            )}

            <h2 className="org-recruiting-card__title">保留中の招待</h2>
            <p className="org-recruiting-count">招待中 {invites.length}人</p>
            {invites.length === 0 ? (
              <p className="org-profile-empty">保留中の招待はありません。</p>
            ) : (
              <ul className="org-recruiting-people">
                {invites.map((row) => {
                  const invitee = row.invitee;
                  const name =
                    invitee?.display_name || invitee?.username || "ユーザー";
                  return (
                    <li key={row.id} className="org-recruiting-person">
                      <div className="org-recruiting-person__identity">
                        {invitee?.avatar_url ? (
                          <img src={invitee.avatar_url} alt="" />
                        ) : (
                          <span aria-hidden="true">{name.slice(0, 1)}</span>
                        )}
                        <div>
                          <strong>{name}</strong>
                          <p>
                            @{invitee?.username || "不明"}
                            {row.created_at
                              ? ` · ${formatRecruitingDate(row.created_at)}`
                              : ""}
                          </p>
                        </div>
                      </div>
                      <div className="org-recruiting-person__actions">
                        <button
                          type="button"
                          className="btn btn-secondary"
                          disabled={busyId != null}
                          onClick={() => void onCancel(row)}
                        >
                          {busyId === row.id ? "取消中…" : "取り消す"}
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </>
        )}
        <Link className="org-edit-back" to={`/orgs/${slug}`}>
          団体プロフィールへ戻る
        </Link>
      </div>
    </div>
  );
}
