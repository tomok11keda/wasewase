import type { RecruitingInvitation } from "./recruitingChat";

type Props = {
  invitation: RecruitingInvitation;
  organizationName?: string;
  busy?: boolean;
  onAccept: () => void;
  onDecline: () => void;
};

export function RecruitingInviteBanner({
  invitation,
  organizationName,
  busy = false,
  onAccept,
  onDecline,
}: Props) {
  const orgName =
    organizationName || invitation.organization_name || "この団体";
  const avatar = invitation.organization_avatar_url;
  const initial = (orgName || "団").slice(0, 1);

  return (
    <section className="org-recruiting-invite-banner" aria-label="新歓チャット招待">
      <div className="org-recruiting-invite-banner__org">
        {avatar ? (
          <img src={avatar} alt="" />
        ) : (
          <span aria-hidden="true">{initial}</span>
        )}
        <div>
          <p className="org-recruiting-invite-banner__lead">
            {orgName}から新歓チャットに招待されました
          </p>
          {invitation.chat_name ? (
            <strong className="org-recruiting-invite-banner__name">
              {invitation.chat_name}
            </strong>
          ) : null}
        </div>
      </div>
      <p className="org-recruiting-invite-banner__hint">
        参加するとメッセージを確認できます。参加するまで本文は表示されません。
      </p>
      <div className="org-recruiting-invite-banner__actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={onAccept}
        >
          {busy ? "処理中…" : "参加する"}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          onClick={onDecline}
        >
          辞退する
        </button>
      </div>
    </section>
  );
}
