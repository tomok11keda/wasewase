import { useReducer, useRef } from "react";
import { Link } from "react-router-dom";
import {
  eventCapacityLabel,
  lotteryResultLabel,
  organizationEventEditPath,
  organizationEventLotteryPath,
  organizationEventManagePath,
  organizationEventRegistrationsPath,
  viewerLotteryRegistrationLabel,
  type OrganizationEvent,
} from "./orgEvents";
import { EventTimelineShareSheet } from "./EventTimelineShareSheet";
import {
  initialTimelineShareUi,
  reduceTimelineShareUi,
} from "./eventTimelineShareFlow";
import { OrgChatSharePicker } from "./OrgChatSharePicker";
import {
  eventDetailAdminActionLabel,
  eventDetailAdminLayout,
  eventPublicationStatusLabel,
  eventSignupModeLabel,
  eventVenueText,
  formatTokyoEventSchedule,
  type EventDetailAdminAction,
} from "./eventDetailPresentation";

type Props = {
  slug: string;
  event: OrganizationEvent;
  showManage: boolean;
  busy: boolean;
  actionError: string | null;
  shareNote: string | null;
  sharePostPath: string | null;
  shareBusy: boolean;
  timelineBusy: boolean;
  onPublish: () => void;
  onUnpublish: () => void;
  onToggleRegistration: () => void;
  onRegister: () => void;
  onUnregister: () => void;
  onDuplicate: () => void;
  onCancelEvent: () => void;
  onDelete: () => void;
  onTimelineShare: (body: string) => Promise<void>;
  onChatShare: (chatIds: number[]) => void | Promise<void>;
};

const STUDENT_LOTTERY_ACTION = "student_lottery" as const;

export function OrganizationEventDetailView({
  slug,
  event,
  showManage,
  busy,
  actionError,
  shareNote,
  sharePostPath,
  shareBusy,
  timelineBusy,
  onPublish,
  onUnpublish,
  onToggleRegistration,
  onRegister,
  onUnregister,
  onDuplicate,
  onCancelEvent,
  onDelete,
  onTimelineShare,
  onChatShare,
}: Props) {
  const [shareUi, dispatchShare] = useReducer(
    reduceTimelineShareUi,
    undefined,
    initialTimelineShareUi
  );
  const shareSubmitLockRef = useRef(false);
  const schedule = formatTokyoEventSchedule(event.starts_at, event.ends_at);
  const venue = eventVenueText(event);
  const description = event.description.trim();
  const layout = eventDetailAdminLayout(event);
  const showStudentCard =
    Boolean(event.viewer_lottery_result) ||
    event.can_view_lottery ||
    event.can_register ||
    event.can_cancel_registration ||
    event.viewer_registered;
  const registrationToggleDisabled =
    busy || (event.has_lottery && !event.registration_open);

  const runAdminAction = (action: EventDetailAdminAction) => {
    switch (action) {
      case "publish":
        onPublish();
        return;
      case "unpublish":
        onUnpublish();
        return;
      case "registration_toggle":
        onToggleRegistration();
        return;
      case "duplicate":
        onDuplicate();
        return;
      case "timeline_share":
        dispatchShare({ type: "tap_open" });
        return;
      case "cancel":
        onCancelEvent();
        return;
      case "delete":
        onDelete();
        return;
      default:
        return;
    }
  };

  const adminHref = (action: EventDetailAdminAction): string | null => {
    if (action === "edit") return organizationEventEditPath(slug, event.id);
    if (action === "registrations") {
      return organizationEventRegistrationsPath(slug, event.id);
    }
    if (action === "run_lottery" || action === "lottery_results") {
      return organizationEventLotteryPath(slug, event.id);
    }
    if (action === "manage") return organizationEventManagePath(slug);
    return null;
  };

  const buttonClass = (action: EventDetailAdminAction, variant: "primary" | "secondary" | "danger") => {
    if (variant === "danger" || action === "cancel" || action === "delete") {
      return "btn btn-danger";
    }
    if (variant === "primary") return "btn btn-primary";
    return "btn btn-secondary";
  };

  const renderAction = (
    action: EventDetailAdminAction,
    variant: "primary" | "secondary" | "danger"
  ) => {
    const label = eventDetailAdminActionLabel(action, event);
    const href = adminHref(action);
    const className = buttonClass(action, variant);
    const disabled =
      (action === "timeline_share" && shareUi.submitting) ||
      (action !== "timeline_share" && busy) ||
      (action === "registration_toggle" && registrationToggleDisabled);
    if (href) {
      return (
        <Link key={action} className={className} to={href}>
          {label}
        </Link>
      );
    }
    return (
      <button
        key={action}
        type="button"
        className={
          action === "timeline_share"
            ? `${className} org-event-timeline-share-open`
            : className
        }
        data-action={action}
        aria-haspopup={action === "timeline_share" ? "dialog" : undefined}
        aria-expanded={
          action === "timeline_share" ? shareUi.composerOpen : undefined
        }
        disabled={disabled}
        onClick={() => runAdminAction(action)}
      >
        {action === "timeline_share" && shareUi.composerOpen
          ? "紹介文を入力"
          : action === "timeline_share" && shareUi.submitting
            ? "シェア中…"
            : busy
              ? "送信中…"
              : label}
      </button>
    );
  };

  return (
    <article
      className="org-event-detail"
      aria-label="イベント詳細"
      data-publication-status={event.status}
      data-signup-mode={event.signup_mode}
    >
      {actionError ? (
        <p className="org-edit-error" role="alert">
          {actionError}
        </p>
      ) : null}
      <section className="org-event-detail__card">
        <p className="org-event-detail__org">{event.organization_name}</p>
        <h1 className="org-event-detail__title">{event.title}</h1>
        {event.status === "cancelled" ? (
          <p className="org-event-detail__cancelled" role="status">
            このイベントは中止されました。
          </p>
        ) : null}
        <ul className="org-event-detail__badges">
          <li
            className={`org-event-badge org-event-badge--${event.status}`}
          >
            {eventPublicationStatusLabel(event.status)}
          </li>
          <li className="org-event-badge org-event-badge--signup">
            {eventSignupModeLabel(event.signup_mode)}
          </li>
          {event.status === "published" && event.is_ended ? (
            <li className="org-event-badge org-event-badge--ended">終了</li>
          ) : null}
          {event.signup_mode === "registration" ? (
            <li className="org-event-badge org-event-badge--count">
              {eventCapacityLabel(event)}
            </li>
          ) : null}
        </ul>
        {event.image_url ? (
          <img
            className="org-event-detail__image"
            src={event.image_url}
            alt=""
          />
        ) : null}
        {schedule.startDateLine ? (
          schedule.sameDay ? (
            <div className="org-event-detail__when">
              <p className="org-event-detail__date">{schedule.startDateLine}</p>
              <p className="org-event-detail__time">{schedule.timeRange}</p>
            </div>
          ) : (
            <div className="org-event-detail__when-split">
              <div>
                <p className="org-event-detail__label">開始</p>
                <p className="org-event-detail__date">{schedule.startDateLine}</p>
                <p className="org-event-detail__time">{schedule.startTime}</p>
              </div>
              <div>
                <p className="org-event-detail__label">終了</p>
                <p className="org-event-detail__date">{schedule.endDateLine}</p>
                <p className="org-event-detail__time">{schedule.endTime}</p>
              </div>
            </div>
          )
        ) : null}
        {venue ? (
          <div className="org-event-detail__field">
            <p className="org-event-detail__label">会場</p>
            <p className="org-event-detail__value">{venue}</p>
          </div>
        ) : null}
        {description ? (
          <div className="org-event-detail__field">
            <p className="org-event-detail__label">説明</p>
            <p className="org-event-detail__value">{description}</p>
          </div>
        ) : null}
      </section>

      {showStudentCard ? (
        <section className="org-event-detail__card" aria-label="参加">
          <div className="org-event-detail__actions">
            {event.viewer_lottery_result ? (
              <p className="org-event-detail__note">
                抽選結果：{lotteryResultLabel(event.viewer_lottery_result)}
                {viewerLotteryRegistrationLabel(event)
                  ? `（${viewerLotteryRegistrationLabel(event)}）`
                  : ""}
              </p>
            ) : null}
            {event.can_view_lottery ? (
              <Link
                className="btn btn-secondary"
                to={organizationEventLotteryPath(slug, event.id)}
                data-action={STUDENT_LOTTERY_ACTION}
              >
                抽選結果を見る
              </Link>
            ) : null}
            {event.can_register ? (
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={onRegister}
              >
                {busy ? "送信中…" : "参加を申し込む"}
              </button>
            ) : null}
            {event.can_cancel_registration ? (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={busy}
                onClick={onUnregister}
              >
                {busy
                  ? "送信中…"
                  : event.has_lottery
                    ? "参加を辞退"
                    : "申し込みを取り消す"}
              </button>
            ) : null}
            {event.viewer_registered && !event.viewer_lottery_result ? (
              <p className="org-event-detail__note">申し込み済みです。</p>
            ) : null}
            {event.can_register || event.can_cancel_registration ? (
              <p className="org-event-privacy">
                抽選を行う場合、氏名・アバター・除外備考が団体チャット内で公開されることがあります。健康情報や連絡先など機微な内容は入力しないでください。
              </p>
            ) : null}
          </div>
        </section>
      ) : null}

      {showManage ? (
        <section className="org-event-detail__card" aria-label="イベント管理">
          {shareNote ? (
            <p className="org-event-detail__note" role="status">
              {shareNote}
              {sharePostPath ? (
                <>
                  {" "}
                  <Link className="org-event-detail__share-link" to={sharePostPath}>
                    投稿を見る
                  </Link>
                </>
              ) : null}
            </p>
          ) : null}
          <div className="org-event-detail__actions">
            {layout.primary === "publish"
              ? renderAction("publish", "primary")
              : null}
            {layout.primary === "timeline_share"
              ? renderAction("timeline_share", "primary")
              : null}
            {layout.secondary.length ? (
              <div
                className={
                  layout.secondary.length > 1
                    ? "org-event-detail__actions org-event-detail__actions--row"
                    : "org-event-detail__actions"
                }
              >
                {layout.secondary.map((action) =>
                  renderAction(action, "secondary")
                )}
              </div>
            ) : null}
            {layout.manage.length ? (
              <div
                className={
                  layout.manage.length > 1
                    ? "org-event-detail__actions org-event-detail__actions--row"
                    : "org-event-detail__actions"
                }
              >
                {layout.manage.map((action) => renderAction(action, "secondary"))}
              </div>
            ) : null}
            {layout.shareChat ? (
              <div className="org-event-share">
                <OrgChatSharePicker
                  slug={slug}
                  busy={shareBusy}
                  submitLabel="選んだチャットにイベントを共有"
                  onShare={onChatShare}
                />
              </div>
            ) : null}
            {layout.more.length || layout.danger.length ? (
              <details className="org-event-more">
                <summary>その他の操作</summary>
                <div className="org-event-more__body">
                  {layout.more.map((action) =>
                    renderAction(action, "secondary")
                  )}
                  {layout.danger.map((action) =>
                    renderAction(action, "danger")
                  )}
                </div>
              </details>
            ) : null}
          </div>
        </section>
      ) : null}

      <p className="org-event-detail__footer">
        <Link className="btn btn-secondary" to={`/orgs/${slug}`}>
          団体プロフィールへ
        </Link>
      </p>
      <EventTimelineShareSheet
        open={shareUi.composerOpen}
        body={shareUi.body}
        submitting={shareUi.submitting || timelineBusy}
        error={shareUi.error || (shareUi.composerOpen ? actionError : null)}
        onBodyChange={(value) => dispatchShare({ type: "edit", body: value })}
        onClose={() => dispatchShare({ type: "close" })}
        onSubmit={() => {
          if (
            shareSubmitLockRef.current ||
            shareUi.submitting ||
            timelineBusy
          ) {
            return;
          }
          shareSubmitLockRef.current = true;
          dispatchShare({ type: "tap_submit" });
          void onTimelineShare(shareUi.body)
            .then(() => {
              dispatchShare({ type: "success" });
            })
            .catch((err: unknown) => {
              dispatchShare({
                type: "failure",
                message:
                  err instanceof Error && err.message
                    ? err.message
                    : "タイムラインにシェアできませんでした。",
              });
            })
            .finally(() => {
              shareSubmitLockRef.current = false;
            });
        }}
      />
    </article>
  );
}
