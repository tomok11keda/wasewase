import { Link } from "react-router-dom";
import {
  parseOrganizationChatEventShareCard,
  recruitingChatEventPath,
  type OrganizationChatEventShareCard,
} from "./orgChatEvents";
import { formatTokyoDateTime } from "./orgEvents";

export function ChatEventShareCard({
  share,
}: {
  share: OrganizationChatEventShareCard | unknown;
}) {
  const parsed = parseOrganizationChatEventShareCard(share);
  if (!parsed || !parsed.content || !parsed.available) {
    return (
      <div className="share-card share-card--unavailable">
        チャット内イベントを表示できません
      </div>
    );
  }
  const content = parsed.content;
  const to =
    content.path ||
    recruitingChatEventPath(
      content.organization_slug,
      content.event_id,
      content.chat_id
    );
  return (
    <Link className="share-card share-card--chat-event" to={to}>
      <p className="share-card__brand">チャット内イベント</p>
      <p className="share-card__title">{content.title || "イベント"}</p>
      {content.starts_at ? (
        <p className="share-card__body">{formatTokyoDateTime(content.starts_at)}</p>
      ) : null}
      {content.venue_name ? (
        <p className="share-card__body">{content.venue_name}</p>
      ) : null}
      <p className="share-card__meta">{content.status_label || "チャット内"}</p>
      <span className="share-card__cta">出欠を確認</span>
    </Link>
  );
}
