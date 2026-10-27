import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ListRowSkeleton } from "../../components/skeleton";
import { OrganizationRequestError } from "./api";
import { RecruitingInviteBanner } from "./RecruitingInviteBanner";
import {
  envelopeChats,
  joinModeLabel,
  listingStatusLabel,
  membershipStatusLabel,
  recruitingChatApplicationsPath,
  recruitingChatCreatePath,
  recruitingChatInvitesPath,
  recruitingChatMembersPath,
  recruitingChatPath,
  recruitingChatSettingsPath,
  shouldShowRecruitingSection,
  visibilityLabel,
  type RecruitingChat,
  type RecruitingChatEnvelope,
} from "./recruitingChat";
import {
  acceptRecruitingInvitation,
  declineRecruitingInvitation,
  joinRecruitingChat,
  leaveRecruitingChat,
  withdrawRecruitingChat,
} from "./recruitingChatApi";

type Props = {
  slug: string;
  envelope: RecruitingChatEnvelope | null;
  loading?: boolean;
  error?: string | null;
  focusedChatId?: number | null;
  /** Hide settings/applications/members — those live on the details screen. */
  hideManageActions?: boolean;
  onReload: () => void | Promise<void>;
  onUpdated: (chat: RecruitingChat) => void;
};

function errorText(err: unknown, fallback: string): string {
  if (err instanceof OrganizationRequestError) return err.message;
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

function ChatCard({
  slug,
  chat,
  canManageOrg,
  hideManageActions,
  busy,
  actionError,
  inviteGone,
  onJoin,
  onWithdraw,
  onLeave,
  onAcceptInvite,
  onDeclineInvite,
}: {
  slug: string;
  chat: RecruitingChat;
  canManageOrg: boolean;
  hideManageActions: boolean;
  busy: string | null;
  actionError: string | null;
  inviteGone: boolean;
  onJoin: () => void;
  onWithdraw: () => void;
  onLeave: () => void;
  onAcceptInvite: () => void;
  onDeclineInvite: () => void;
}) {
  const canManage = Boolean(canManageOrg || chat.can_manage);
  const closed =
    chat.membership_status === "closed" || chat.listing_status === "closed";
  const status = chat.membership_status;
  const invitation = chat.invitation;
  const showInvite = status === "invited" && invitation && !inviteGone;
  const showJoin = chat.can_join && status === "not_joined" && !showInvite;
  const showApply =
    chat.can_apply &&
    (status === "not_joined" || status === "rejected") &&
    !showInvite;
  const showOpen = Boolean(chat.room_id) && (status === "joined" || canManage);
  const chatId = chat.id;

  return (
    <article className="org-recruiting-card" aria-label={chat.name || "団体チャット"}>
      {chat.name ? <h3 className="org-recruiting-card__name">{chat.name}</h3> : null}
      {chat.description ? (
        <p className="org-recruiting-card__description">{chat.description}</p>
      ) : null}
      <ul className="org-recruiting-card__meta">
        <li>{visibilityLabel(chat.visibility)}</li>
        <li>{joinModeLabel(chat.join_mode)}</li>
        {chat.visibility === "public" ? (
          <li>{listingStatusLabel(chat.listing_status)}</li>
        ) : null}
        {chat.name || chat.member_count > 0 ? (
          <li>参加者 {chat.member_count}人</li>
        ) : null}
        <li>{membershipStatusLabel(status)}</li>
      </ul>
      {closed && status !== "joined" && status !== "invited" && !canManage ? (
        <p className="org-recruiting-card__closed" role="status">
          現在は新規参加を受け付けていません。
        </p>
      ) : null}
      {status === "rejected" ? (
        <p className="org-recruiting-card__rejected" role="status">
          参加が承認されませんでした。
        </p>
      ) : null}
      {actionError ? (
        <p className="org-recruiting-card__error" role="alert">
          {actionError}
        </p>
      ) : null}
      {showInvite && invitation ? (
        <RecruitingInviteBanner
          invitation={invitation}
          busy={Boolean(busy)}
          onAccept={onAcceptInvite}
          onDecline={onDeclineInvite}
        />
      ) : null}
      <div className="org-recruiting-card__actions">
        {showJoin ? (
          <button
            type="button"
            className="btn btn-primary"
            disabled={Boolean(busy)}
            onClick={onJoin}
          >
            {busy === "join" ? "参加中…" : "団体チャットに参加"}
          </button>
        ) : null}
        {showApply ? (
          <button
            type="button"
            className="btn btn-primary"
            disabled={Boolean(busy)}
            onClick={onJoin}
          >
            {busy === "join"
              ? "申請中…"
              : status === "rejected"
                ? "再申請する"
                : "参加を申請する"}
          </button>
        ) : null}
        {status === "pending" ? (
          <>
            <span className="org-recruiting-card__pending">承認待ち</span>
            {chat.can_withdraw ? (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={Boolean(busy)}
                onClick={onWithdraw}
              >
                {busy === "withdraw" ? "取下げ中…" : "申請を取り下げる"}
              </button>
            ) : null}
          </>
        ) : null}
        {showOpen ? (
          <Link className="btn btn-primary" to={recruitingChatPath(slug, chatId)}>
            チャットを開く
          </Link>
        ) : null}
        {chat.can_leave ? (
          <button
            type="button"
            className="btn btn-secondary"
            disabled={Boolean(busy)}
            onClick={onLeave}
          >
            {busy === "leave" ? "退出中…" : "退出する"}
          </button>
        ) : null}
        {canManage && !hideManageActions ? (
          <>
            <Link
              className="btn btn-secondary"
              to={recruitingChatSettingsPath(slug, chatId)}
            >
              設定
            </Link>
            <Link
              className="btn btn-secondary"
              to={recruitingChatApplicationsPath(slug, chatId)}
            >
              申請管理
              {typeof chat.pending_count === "number" && chat.pending_count > 0
                ? `（${chat.pending_count}）`
                : ""}
            </Link>
            <Link
              className="btn btn-secondary"
              to={recruitingChatMembersPath(slug, chatId)}
            >
              参加者管理
            </Link>
            <Link
              className="btn btn-secondary"
              to={recruitingChatInvitesPath(slug, chatId)}
            >
              学生を招待
            </Link>
          </>
        ) : null}
      </div>
    </article>
  );
}

export function RecruitingChatSection({
  slug,
  envelope,
  loading = false,
  error = null,
  focusedChatId = null,
  hideManageActions = false,
  onReload,
  onUpdated,
}: Props) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [inviteGone, setInviteGone] = useState(false);
  const busyRef = useRef(false);

  useEffect(() => {
    setActionError(null);
    setInviteGone(false);
  }, [slug, focusedChatId, envelope?.recruiting_chat?.id]);

  if (loading && !shouldShowRecruitingSection(envelope)) {
    return null;
  }

  if (loading) {
    return (
      <section className="org-recruiting-card" aria-label="団体チャット">
        <h2 className="org-recruiting-card__title">団体チャット</h2>
        <ListRowSkeleton rows={3} />
      </section>
    );
  }

  if (error) {
    return (
      <section className="org-recruiting-card" aria-label="団体チャット">
        <h2 className="org-recruiting-card__title">団体チャット</h2>
        <p className="org-profile-empty">{error}</p>
        <button type="button" className="btn btn-secondary" onClick={() => void onReload()}>
          再試行
        </button>
      </section>
    );
  }

  if (!shouldShowRecruitingSection(envelope)) {
    return null;
  }

  const chats = envelopeChats(envelope);
  const focused =
    focusedChatId != null
      ? chats.find((row) => row.id === focusedChatId) || envelope?.recruiting_chat || null
      : chats.length === 1
        ? chats[0]
        : null;
  const visibleChats = focused ? [focused] : chats;
  const canManage = Boolean(envelope?.can_manage);
  const showList = !focused && (canManage || chats.length !== 1);

  const run = async (key: string, fn: () => Promise<RecruitingChat>) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(key);
    setActionError(null);
    try {
      const next = await fn();
      onUpdated(next);
    } catch (err) {
      setActionError(errorText(err, "操作に失敗しました。"));
    } finally {
      busyRef.current = false;
      setBusy(null);
    }
  };

  if (!visibleChats.length) {
    return (
      <section className="org-recruiting-card" aria-label="団体チャット">
        <h2 className="org-recruiting-card__title">団体チャット</h2>
        <p className="org-recruiting-card__lead">
          まだ団体チャットは作成されていません。
        </p>
        {envelope?.can_create ? (
          <div className="org-recruiting-card__actions">
            <Link className="btn btn-primary" to={recruitingChatCreatePath(slug)}>
              団体チャットを作成
            </Link>
          </div>
        ) : null}
      </section>
    );
  }

  return (
    <section className="org-recruiting-list" aria-label="団体チャット">
      <h2 className="org-recruiting-card__title">団体チャット</h2>
      {showList && envelope?.can_create ? (
        <p className="org-recruiting-card__actions">
          <Link className="btn btn-secondary" to={recruitingChatCreatePath(slug)}>
            新しいチャットを作成
          </Link>
        </p>
      ) : null}
      {visibleChats.map((chat) => (
        <ChatCard
          key={chat.id ?? chat.name}
          slug={slug}
          chat={chat}
          canManageOrg={canManage}
          hideManageActions={hideManageActions}
          busy={busy}
          actionError={actionError}
          inviteGone={inviteGone}
          onJoin={() =>
            void run("join", () => joinRecruitingChat(slug, chat.id))
          }
          onWithdraw={() => {
            if (!window.confirm("参加申請を取り下げますか？")) return;
            void run("withdraw", () => withdrawRecruitingChat(slug, chat.id));
          }}
          onLeave={() => {
            if (
              !window.confirm(
                "団体チャットから退出しますか？退出するとメッセージを読めなくなります。"
              )
            ) {
              return;
            }
            void run("leave", () => leaveRecruitingChat(slug, chat.id));
          }}
          onAcceptInvite={() => {
            const invitation = chat.invitation;
            if (!invitation) return;
            void run("accept", async () => {
              const next = await acceptRecruitingInvitation(invitation.id);
              navigate(recruitingChatPath(slug, next.id || chat.id));
              return next;
            });
          }}
          onDeclineInvite={() => {
            const invitation = chat.invitation;
            if (!invitation) return;
            if (!window.confirm("この招待を辞退しますか？")) return;
            void run("decline", async () => {
              await declineRecruitingInvitation(invitation.id);
              setInviteGone(true);
              return { ...chat, membership_status: "not_joined", invitation: null };
            });
          }}
        />
      ))}
    </section>
  );
}
