import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import { RecruitingManageNav } from "../features/orgs/RecruitingManageNav";
import {
  canShowRecruitingManageNav,
  formatRecruitingDate,
  type RecruitingMember,
} from "../features/orgs/recruitingChat";
import {
  fetchRecruitingChat,
  fetchRecruitingMembers,
  removeRecruitingMember,
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

export function OrganizationRecruitingChatMembersPage() {
  const { slug } = useParams();
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const [members, setMembers] = useState<RecruitingMember[]>([]);
  const [canManage, setCanManage] = useState(false);
  const [pendingCount, setPendingCount] = useState<number | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const busyRef = useRef(false);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setMembers([]);
    setCanManage(false);
    setPendingCount(undefined);
    setLoading(true);
    setError(null);
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
      const manage = envelope.can_manage || Boolean(envelope.recruiting_chat?.can_manage);
      setCanManage(manage);
      setPendingCount(envelope.recruiting_chat?.pending_count);
      if (!manage) {
        setError("forbidden");
        setMembers([]);
        return;
      }
      const rows = await fetchRecruitingMembers(slug);
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setMembers(rows);
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setMembers([]);
      setCanManage(false);
      setPendingCount(undefined);
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

  if (!slug) return <Navigate to="/" replace />;
  const loginNext = `/app/organizations/${slug}/recruiting-chat/members`;

  if (browsePreview || (!sessionLoading && !me?.authenticated)) {
    return (
      <div className="org-edit-page" data-spa-page="新歓チャット参加者">
        <div className="main-inner">
          <p>参加者管理にはログインが必要です。</p>
          <Link className="btn btn-primary" to={spaLoginPath(loginNext)}>
            ログイン
          </Link>
        </div>
      </div>
    );
  }

  const onRemove = (member: RecruitingMember) => {
    if (member.user_id == null) return;
    const name = member.display_name || member.username || "この参加者";
    if (!window.confirm(`${name}さんを新歓チャットから除外しますか？`)) return;
    if (busyRef.current) return;
    busyRef.current = true;
    setBusyId(member.user_id);
    setError(null);
    void (async () => {
      try {
        await removeRecruitingMember(slug, member.user_id as number);
        setMembers(await fetchRecruitingMembers(slug));
      } catch (err) {
        setError(errorText(err, "除外できませんでした。"));
      } finally {
        busyRef.current = false;
        setBusyId(null);
      }
    })();
  };

  return (
    <div className="org-edit-page org-recruiting-manage-page" data-spa-page="新歓チャット参加者">
      <div className="main-inner">
        <p className="form-lead">新歓チャットの参加者です。除外するとメッセージを読めなくなります。</p>
        {canShowRecruitingManageNav({
          hydrated: !loading && !sessionLoading,
          canManage,
        }) ? (
          <RecruitingManageNav slug={slug} pendingCount={pendingCount} />
        ) : null}
        {loading || sessionLoading ? (
          <PeopleListSkeleton />
        ) : error === "forbidden" || error === "not_found" ? (
          <p>参加者を管理する権限がありません。</p>
        ) : (
          <>
            {error ? (
              <p className="org-edit-error" role="alert">
                {error}
              </p>
            ) : null}
            <p className="org-recruiting-count">参加者 {members.length}人</p>
            {members.length === 0 ? (
              <p className="org-profile-empty">参加者はまだいません。</p>
            ) : (
              <ul className="org-recruiting-people">
                {members.map((row) => {
                  const name = row.display_name || row.username || "ユーザー";
                  return (
                    <li
                      key={`${row.user_id}-${row.username}`}
                      className="org-recruiting-person"
                    >
                      <div className="org-recruiting-person__identity">
                        {row.avatar_url ? (
                          <img src={row.avatar_url} alt="" />
                        ) : (
                          <span aria-hidden="true">{name.slice(0, 1)}</span>
                        )}
                        <div>
                          {row.user_id ? (
                            <Link to={`/users/${row.user_id}/posts`}>{name}</Link>
                          ) : (
                            <strong>{name}</strong>
                          )}
                          <p>{formatRecruitingDate(row.joined_at)}</p>
                        </div>
                      </div>
                      {canManage && row.user_id != null ? (
                        <div className="org-recruiting-person__actions">
                          <button
                            type="button"
                            className="btn btn-secondary"
                            disabled={busyId != null}
                            onClick={() => onRemove(row)}
                          >
                            {busyId === row.user_id ? "除外中…" : "除外"}
                          </button>
                        </div>
                      ) : null}
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
