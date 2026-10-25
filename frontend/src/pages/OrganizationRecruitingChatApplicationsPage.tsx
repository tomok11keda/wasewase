import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import { RecruitingManageNav } from "../features/orgs/RecruitingManageNav";
import {
  canShowRecruitingManageNav,
  formatRecruitingDate,
  type RecruitingApplication,
} from "../features/orgs/recruitingChat";
import {
  approveRecruitingApplication,
  fetchRecruitingApplications,
  fetchRecruitingChat,
  rejectRecruitingApplication,
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

export function OrganizationRecruitingChatApplicationsPage() {
  const { slug } = useParams();
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const [applications, setApplications] = useState<RecruitingApplication[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [canManage, setCanManage] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const busyRef = useRef(false);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setApplications([]);
    setPendingCount(0);
    setCanManage(false);
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
      const manage =
        envelope.can_manage || Boolean(envelope.recruiting_chat?.can_manage);
      setCanManage(manage);
      if (!manage) {
        setError("forbidden");
        setApplications([]);
        return;
      }
      const data = await fetchRecruitingApplications(slug, "pending");
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setApplications(data.applications);
      setPendingCount(data.pending_count);
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setApplications([]);
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

  if (!slug) return <Navigate to="/" replace />;
  const loginNext = `/app/organizations/${slug}/recruiting-chat/applications`;

  if (browsePreview || (!sessionLoading && !me?.authenticated)) {
    return (
      <div className="org-edit-page" data-spa-page="団体チャット申請">
        <div className="main-inner">
          <p>申請管理にはログインが必要です。</p>
          <Link className="btn btn-primary" to={spaLoginPath(loginNext)}>
            ログイン
          </Link>
        </div>
      </div>
    );
  }

  const act = async (
    applicationId: number,
    fn: () => Promise<unknown>
  ) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusyId(applicationId);
    setError(null);
    try {
      await fn();
      const data = await fetchRecruitingApplications(slug, "pending");
      setApplications(data.applications);
      setPendingCount(data.pending_count);
    } catch (err) {
      setError(errorText(err, "申請を処理できませんでした。"));
    } finally {
      busyRef.current = false;
      setBusyId(null);
    }
  };

  return (
    <div className="org-edit-page org-recruiting-manage-page" data-spa-page="団体チャット申請">
      <div className="main-inner">
        <p className="form-lead">承認待ちの参加申請です。メールアドレスは表示しません。</p>
        {canShowRecruitingManageNav({
          hydrated: !loading && !sessionLoading,
          canManage,
        }) ? (
          <RecruitingManageNav slug={slug} pendingCount={pendingCount} />
        ) : null}
        {loading || sessionLoading ? (
          <PeopleListSkeleton />
        ) : error === "forbidden" || error === "not_found" ? (
          <p>申請を管理する権限がありません。</p>
        ) : error && applications.length === 0 && error !== "load_failed" ? (
          <p className="org-edit-error" role="alert">
            {error}
          </p>
        ) : (
          <>
            {error ? (
              <p className="org-edit-error" role="alert">
                {error}
              </p>
            ) : null}
            <p className="org-recruiting-count">承認待ち {pendingCount}件</p>
            {applications.length === 0 ? (
              <p className="org-profile-empty">承認待ちの申請はありません。</p>
            ) : (
              <ul className="org-recruiting-people">
                {applications.map((row) => {
                  const name = row.display_name || row.username || "ユーザー";
                  return (
                    <li key={row.id} className="org-recruiting-person">
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
                          <p>{formatRecruitingDate(row.created_at)}</p>
                        </div>
                      </div>
                      <div className="org-recruiting-person__actions">
                        <button
                          type="button"
                          className="btn btn-primary"
                          disabled={busyId != null}
                          onClick={() =>
                            void act(row.id, () =>
                              approveRecruitingApplication(slug, row.id)
                            )
                          }
                        >
                          {busyId === row.id ? "処理中…" : "承認"}
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary"
                          disabled={busyId != null}
                          onClick={() =>
                            void act(row.id, () =>
                              rejectRecruitingApplication(slug, row.id)
                            )
                          }
                        >
                          拒否
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
