import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { OrganizationRequestError } from "./api";
import {
  joinModeLabel,
  listingStatusLabel,
  membershipStatusLabel,
  recruitingChatApplicationsPath,
  recruitingChatMembersPath,
  recruitingChatPath,
  recruitingChatSettingsPath,
  shouldShowRecruitingSection,
  type RecruitingChat,
  type RecruitingChatEnvelope,
} from "./recruitingChat";
import {
  joinRecruitingChat,
  leaveRecruitingChat,
  withdrawRecruitingChat,
} from "./recruitingChatApi";

type Props = {
  slug: string;
  envelope: RecruitingChatEnvelope | null;
  loading?: boolean;
  error?: string | null;
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

export function RecruitingChatSection({
  slug,
  envelope,
  loading = false,
  error = null,
  hideManageActions = false,
  onReload,
  onUpdated,
}: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const busyRef = useRef(false);

  useEffect(() => {
    setActionError(null);
  }, [slug, envelope?.recruiting_chat?.id]);

  if (loading && !shouldShowRecruitingSection(envelope)) {
    return null;
  }

  if (loading) {
    return (
      <section className="org-recruiting-card" aria-label="新歓チャット">
        <h2 className="org-recruiting-card__title">新歓チャット</h2>
        <p className="org-profile-empty">新歓チャットを読み込み中…</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="org-recruiting-card" aria-label="新歓チャット">
        <h2 className="org-recruiting-card__title">新歓チャット</h2>
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

  const chat = envelope?.recruiting_chat ?? null;
  const canManage = Boolean(envelope?.can_manage || chat?.can_manage);
  const closed =
    chat?.membership_status === "closed" || chat?.listing_status === "closed";

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

  const onJoin = () => void run("join", () => joinRecruitingChat(slug));
  const onWithdraw = () => {
    if (!window.confirm("参加申請を取り下げますか？")) return;
    void run("withdraw", () => withdrawRecruitingChat(slug));
  };
  const onLeave = () => {
    if (
      !window.confirm(
        "新歓チャットから退出しますか？退出するとメッセージを読めなくなります。"
      )
    ) {
      return;
    }
    void run("leave", () => leaveRecruitingChat(slug));
  };

  if (!chat) {
    return (
      <section className="org-recruiting-card" aria-label="新歓チャット">
        <h2 className="org-recruiting-card__title">新歓チャット</h2>
        <p className="org-recruiting-card__lead">
          まだ新歓チャットは作成されていません。
        </p>
        {envelope?.can_create ? (
          <div className="org-recruiting-card__actions">
            <Link className="btn btn-primary" to={recruitingChatSettingsPath(slug)}>
              新歓チャットを作成
            </Link>
          </div>
        ) : null}
      </section>
    );
  }

  const status = chat.membership_status;
  const showJoin = chat.can_join && status === "not_joined";
  const showApply =
    chat.can_apply && (status === "not_joined" || status === "rejected");
  const showOpen = Boolean(chat.room_id) && (status === "joined" || canManage);

  return (
    <section className="org-recruiting-card" aria-label="新歓チャット">
      <h2 className="org-recruiting-card__title">新歓チャット</h2>
      {chat.name ? <h3 className="org-recruiting-card__name">{chat.name}</h3> : null}
      {chat.description ? (
        <p className="org-recruiting-card__description">{chat.description}</p>
      ) : null}
      <ul className="org-recruiting-card__meta">
        <li>{joinModeLabel(chat.join_mode)}</li>
        <li>{listingStatusLabel(chat.listing_status)}</li>
        {chat.name || chat.member_count > 0 ? (
          <li>参加者 {chat.member_count}人</li>
        ) : null}
        <li>{membershipStatusLabel(status)}</li>
      </ul>
      {closed && status !== "joined" && !canManage ? (
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
      <div className="org-recruiting-card__actions">
        {showJoin ? (
          <button
            type="button"
            className="btn btn-primary"
            disabled={Boolean(busy)}
            onClick={onJoin}
          >
            {busy === "join" ? "参加中…" : "新歓チャットに参加"}
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
          <Link className="btn btn-primary" to={recruitingChatPath(slug)}>
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
            <Link className="btn btn-secondary" to={recruitingChatSettingsPath(slug)}>
              設定
            </Link>
            <Link
              className="btn btn-secondary"
              to={recruitingChatApplicationsPath(slug)}
            >
              申請管理
              {typeof chat.pending_count === "number" && chat.pending_count > 0
                ? `（${chat.pending_count}）`
                : ""}
            </Link>
            <Link className="btn btn-secondary" to={recruitingChatMembersPath(slug)}>
              参加者管理
            </Link>
          </>
        ) : null}
      </div>
    </section>
  );
}
