import { Link } from "react-router-dom";
import {
  parseOrganizationEventLotteryShareCard,
  type OrganizationEventLotteryShareCard,
} from "./orgEvents";

export function LotteryShareCard({
  share,
}: {
  share: OrganizationEventLotteryShareCard | unknown;
}) {
  const parsed =
    share && typeof share === "object" && "type" in share && share.type === "org_event_lottery"
      ? parseOrganizationEventLotteryShareCard(share)
      : parseOrganizationEventLotteryShareCard(share);
  if (!parsed || !parsed.content || !parsed.available) {
    return <div className="share-card share-card--unavailable">抽選結果を表示できません</div>;
  }
  const content = parsed.content;
  const to =
    content.path ||
    (content.organization_slug && content.event_id
      ? `/organizations/${content.organization_slug}/events/${content.event_id}/lottery`
      : "/dm");
  return (
    <Link className="share-card share-card--lottery" to={to}>
      <p className="share-card__brand">抽選結果</p>
      <p className="share-card__title">{content.title || "イベント"}</p>
      <p className="share-card__body">
        応募 {content.applicant_count}人 · 対象 {content.eligible_count}人
      </p>
      <p className="share-card__body">
        当選 {content.winner_count}人 · 落選 {content.not_selected_count}人 · 対象外{" "}
        {content.excluded_count}人
      </p>
      <span className="share-card__cta">抽選結果を見る</span>
    </Link>
  );
}
