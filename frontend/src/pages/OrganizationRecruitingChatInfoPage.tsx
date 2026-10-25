import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { spaLoginPath } from "../features/auth/api";
import {
  fetchOrganizationProfile,
  OrganizationRequestError,
} from "../features/orgs/api";
import { organizationInitial } from "../features/orgs/orgProfile";
import {
  joinModeLabel,
  listingStatusLabel,
  recruitingChatApplicationsPath,
  recruitingChatInvitesPath,
  recruitingChatMembersPath,
  recruitingChatPath,
  recruitingChatSettingsPath,
  type RecruitingChat,
} from "../features/orgs/recruitingChat";
import {
  fetchRecruitingChat,
  leaveRecruitingChat,
} from "../features/orgs/recruitingChatApi";
import { isBrowsePreview, useSession } from "../lib/session";
import { ChatInfoHeroSkeleton, ListRowSkeleton } from "../components/skeleton";
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

export function OrganizationRecruitingChatInfoPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const sessionUserId =
    me?.authenticated && me.user?.id != null ? me.user.id : null;
  const userIdRef = useRef(sessionUserId);
  userIdRef.current = sessionUserId;
  const fetchGen = useRef(0);
  const [chat, setChat] = useState<RecruitingChat | null>(null);
  const [canManage, setCanManage] = useState(false);
  const [orgName, setOrgName] = useState("");
  const [orgAvatar, setOrgAvatar] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [leaveBusy, setLeaveBusy] = useState(false);

  useLayoutEffect(() => {
    nextRequestId(fetchGen);
    setChat(null);
    setCanManage(false);
    setOrgName("");
    setOrgAvatar("");
    setLoading(true);
    setError(null);
  }, [slug, sessionUserId]);

  const load = useCallback(async () => {
    if (!slug) {
      setError("not_found");
      setLoading(false);
      return;
    }
    const gen = nextRequestId(fetchGen);
    const startedUserId = userIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const [envelope, profile] = await Promise.all([
        fetchRecruitingChat(slug),
        fetchOrganizationProfile(slug).catch(() => null),
      ]);
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setChat(envelope.recruiting_chat);
      setCanManage(
        envelope.can_manage || Boolean(envelope.recruiting_chat?.can_manage)
      );
      if (profile) {
        setOrgName(profile.organization.name);
        setOrgAvatar(profile.organization.avatar_url);
      }
    } catch (err) {
      if (!isLatestRequest(fetchGen, gen)) return;
      if (!isSameUserScope(startedUserId, userIdRef.current)) return;
      setChat(null);
      setCanManage(false);
      setOrgName("");
      setOrgAvatar("");
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
  const loginNext = `/app/organizations/${slug}/recruiting-chat/info`;

  if (browsePreview || (!sessionLoading && !me?.authenticated)) {
    return (
      <div className="dm-page chat-info-page" data-spa-page="新歓チャット詳細">
        <div className="main-inner">
          <p>チャット詳細はログイン後に利用できます。</p>
          <Link className="btn btn-primary" to={spaLoginPath(loginNext)}>
            ログイン
          </Link>
        </div>
      </div>
    );
  }

  const onLeave = async () => {
    if (
      !window.confirm(
        "新歓チャットから退出しますか？退出するとメッセージを読めなくなります。"
      )
    ) {
      return;
    }
    setLeaveBusy(true);
    try {
      const next = await leaveRecruitingChat(slug);
      setChat(next);
      navigate(recruitingChatPath(slug), { replace: true });
    } catch (err) {
      window.alert(errorText(err, "退出に失敗しました"));
    } finally {
      setLeaveBusy(false);
    }
  };

  const title = chat?.name || "新歓チャット";
  const orgLabel = orgName || "";
  const initial = organizationInitial(orgLabel || title);

  return (
    <div className="dm-page chat-info-page" data-spa-page="新歓チャット詳細">
      <div className="main-inner">
        {loading || sessionLoading ? (
          <>
            <ChatInfoHeroSkeleton rounded />
            <ListRowSkeleton rows={4} />
          </>
        ) : error === "forbidden" || error === "not_found" ? (
          <p>このチャットを表示する権限がありません。</p>
        ) : error && !chat ? (
          <p className="org-edit-error" role="alert">
            {errorText(error, "読み込みに失敗しました。")}
          </p>
        ) : (
          <>
            <section className="chat-info-hero">
              {orgAvatar ? (
                <span className="chat-info-hero__avatar chat-info-hero__avatar--rounded">
                  <img src={orgAvatar} alt="" />
                </span>
              ) : (
                <span className="chat-info-hero__avatar chat-info-hero__avatar--rounded">
                  {initial}
                </span>
              )}
              <h1>{title}</h1>
              <p>
                {orgLabel ? `${orgLabel} · ` : ""}
                新歓チャット
                {typeof chat?.member_count === "number"
                  ? ` · ${chat.member_count}人`
                  : ""}
              </p>
              {chat?.description ? <p>{chat.description}</p> : null}
              {chat ? (
                <p>
                  {joinModeLabel(chat.join_mode)} ·{" "}
                  {listingStatusLabel(chat.listing_status)}
                </p>
              ) : null}
            </section>

            <ul className="chat-info-list">
              {orgLabel ? (
                <li>
                  <Link to={`/orgs/${slug}`}>
                    団体プロフィール
                    <span aria-hidden="true">›</span>
                  </Link>
                </li>
              ) : null}
              {canManage ? (
                <>
                  <li>
                    <Link to={recruitingChatSettingsPath(slug)}>
                      チャット設定
                      <span aria-hidden="true">›</span>
                    </Link>
                  </li>
                  <li>
                    <Link to={recruitingChatApplicationsPath(slug)}>
                      申請管理
                      {typeof chat?.pending_count === "number" &&
                      chat.pending_count > 0
                        ? `（${chat.pending_count}）`
                        : ""}
                      <span aria-hidden="true">›</span>
                    </Link>
                  </li>
                  <li>
                    <Link to={recruitingChatMembersPath(slug)}>
                      参加者管理
                      <span aria-hidden="true">›</span>
                    </Link>
                  </li>
                  <li>
                    <Link to={recruitingChatInvitesPath(slug)}>
                      学生を招待
                      <span aria-hidden="true">›</span>
                    </Link>
                  </li>
                </>
              ) : null}
              {chat?.can_leave ? (
                <li>
                  <button
                    type="button"
                    className="is-danger"
                    disabled={leaveBusy}
                    onClick={() => void onLeave()}
                  >
                    {leaveBusy ? "退出中…" : "退出する"}
                  </button>
                </li>
              ) : null}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
