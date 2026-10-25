import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { spaLoginPath } from "../features/auth/api";
import { OrganizationRequestError } from "../features/orgs/api";
import { RecruitingInviteBanner } from "../features/orgs/RecruitingInviteBanner";
import {
  recruitingChatErrorMessage,
  recruitingChatPath,
  recruitingInviteOpenState,
  type RecruitingInvitation,
} from "../features/orgs/recruitingChat";
import {
  acceptRecruitingInvitation,
  declineRecruitingInvitation,
  fetchViewerRecruitingInvitation,
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

export function OrganizationRecruitingChatInvitePage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const busyRef = useRef(false);
  const [invitation, setInvitation] = useState<RecruitingInvitation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setInvitation(null);
    setError(null);
    setLoading(true);
  }, [slug, sessionUserId]);

  const load = useCallback(async () => {
    if (!slug) return;
    const gen = nextRequestId(fetchGen);
    const startedUserId = userIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchViewerRecruitingInvitation(slug);
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      if (data.recruiting_chat?.room_id && data.recruiting_chat.can_send) {
        navigate(recruitingChatPath(slug), { replace: true });
        return;
      }
      setInvitation(data.invitation);
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setInvitation(null);
      setError(err instanceof OrganizationRequestError ? err.code : "load_failed");
    } finally {
      if (isLatestRequest(fetchGen, gen)) setLoading(false);
    }
  }, [navigate, slug]);

  useEffect(() => {
    if (sessionLoading || browsePreview) return;
    void load();
  }, [browsePreview, load, sessionLoading, sessionUserId]);

  if (!slug) return <Navigate to="/" replace />;
  const loginNext = `/app/organizations/${slug}/recruiting-chat/invite`;

  if (browsePreview || (!sessionLoading && !me?.authenticated)) {
    return (
      <div className="org-edit-page" data-spa-page="新歓チャット招待">
        <div className="main-inner">
          <p>招待の確認にはログインが必要です。</p>
          <Link className="btn btn-primary" to={spaLoginPath(loginNext)}>
            ログイン
          </Link>
        </div>
      </div>
    );
  }

  const run = async (fn: () => Promise<void>) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(errorText(err, "操作に失敗しました。"));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const onAccept = () => {
    if (!invitation) return;
    void run(async () => {
      const chat = await acceptRecruitingInvitation(invitation.id);
      if (chat.room_id) {
        navigate(recruitingChatPath(slug), { replace: true });
        return;
      }
      navigate(`/orgs/${slug}`, { replace: true });
    });
  };

  const onDecline = () => {
    if (!invitation) return;
    if (!window.confirm("この招待を辞退しますか？")) return;
    void run(async () => {
      await declineRecruitingInvitation(invitation.id);
      navigate("/dm", { replace: true });
    });
  };

  const view = recruitingInviteOpenState({
    authenticated: true,
    error,
    invitation,
  });

  return (
    <div className="org-edit-page" data-spa-page="新歓チャット招待">
      <div className="main-inner">
        {loading || sessionLoading ? (
          <PeopleListSkeleton />
        ) : view === "responded" ? (
          <section className="org-recruiting-card" aria-label="新歓チャット招待">
            <h1 className="org-recruiting-card__title">招待を確認できません</h1>
            <p className="org-recruiting-card__lead">
              この招待は取り消されたか、すでに応答済みです。
            </p>
            <Link className="btn btn-secondary" to={`/orgs/${slug}`}>
              団体プロフィールへ
            </Link>
          </section>
        ) : view === "pending" && invitation ? (
          <>
            {error ? (
              <p className="org-edit-error" role="alert">
                {recruitingChatErrorMessage(error, error)}
              </p>
            ) : null}
            <RecruitingInviteBanner
              invitation={invitation}
              busy={busy}
              onAccept={onAccept}
              onDecline={onDecline}
            />
          </>
        ) : view === "error" ? (
          <p className="org-edit-error" role="alert">
            {recruitingChatErrorMessage(error || undefined, "招待を読み込めませんでした。")}
          </p>
        ) : (
          <p className="org-profile-empty">招待が見つかりません。</p>
        )}
      </div>
    </div>
  );
}
