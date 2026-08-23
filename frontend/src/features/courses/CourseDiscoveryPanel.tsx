import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import type { CourseDiscoverCard } from "./api";
import { analytics } from "../../lib/analytics/events";

type SectionKey = "enrolled" | "active" | "popular";

function CourseDiscoverCardView({
  card,
  section,
  rank,
}: {
  card: CourseDiscoverCard;
  section: SectionKey;
  rank: number;
}) {
  const talkHint =
    card.talk_today_count > 0
      ? `今日 ${card.talk_today_count}件のトーク`
      : card.talk_recent_count > 0
        ? `新着 ${card.talk_recent_count}件`
        : null;

  return (
    <Link
      className="course-discover-card"
      to={`/courses/${card.id}`}
      onClick={() =>
        analytics.courseDiscoveryCardOpened({
          offering_id: card.id,
          source_section: section,
          rank,
        })
      }
    >
      <h3 className="course-discover-card__title">{card.title}</h3>
      <p className="course-discover-card__instructor">{card.instructor}</p>
      <p className="course-discover-card__schedule">
        {card.schedule_label || "—"}
        {card.semester_label ? ` · ${card.semester_label}` : ""}
      </p>
      <p className="course-discover-card__stats">
        履修中 {card.enrollment_count}人
        {card.review_count > 0 ? (
          <>
            {" · "}
            ⭐ {card.review_overall ?? "—"}
            {" · "}
            レビュー{card.review_count}件
          </>
        ) : (
          " · レビューなし"
        )}
      </p>
      {talkHint ? (
        <p className="course-discover-card__talk">{talkHint}</p>
      ) : null}
    </Link>
  );
}

function Section({
  title,
  section,
  cards,
  empty,
}: {
  title: string;
  section: SectionKey;
  cards: CourseDiscoverCard[];
  empty: ReactNode;
}) {
  return (
    <section className="course-discover-section" aria-label={title}>
      <h3 className="course-discover-section__title">{title}</h3>
      {cards.length === 0 ? (
        <div className="course-discover-empty">{empty}</div>
      ) : (
        <ul className="course-discover-list">
          {cards.map((card, index) => (
            <li key={`${section}-${card.id}`}>
              <CourseDiscoverCardView
                card={card}
                section={section}
                rank={index + 1}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

type Props = {
  enrolled: CourseDiscoverCard[];
  active: CourseDiscoverCard[];
  popular: CourseDiscoverCard[];
  loading: boolean;
  error: string | null;
  authenticated: boolean;
};

export function CourseDiscoveryPanel({
  enrolled,
  active,
  popular,
  loading,
  error,
  authenticated,
}: Props) {
  if (loading) {
    return (
      <div className="course-discover" aria-busy="true">
        <div className="course-discover-skeleton" />
        <div className="course-discover-skeleton" />
        <div className="course-discover-skeleton" />
      </div>
    );
  }

  if (error) {
    return (
      <p className="empty-message">読み込みに失敗しました（{error}）</p>
    );
  }

  const allEmpty =
    enrolled.length === 0 && active.length === 0 && popular.length === 0;

  if (allEmpty) {
    return (
      <div className="course-discover-global-empty">
        <p>まだ発見できる授業が少ないようです。</p>
        <Link className="course-discover-cta" to="/timetable">
          時間割に授業を追加してみよう
        </Link>
      </div>
    );
  }

  return (
    <div className="course-discover">
      <Section
        title="履修中の授業"
        section="enrolled"
        cards={enrolled}
        empty={
          authenticated ? (
            <>
              <p>時間割に授業を追加するとここに表示されます</p>
              <Link className="course-discover-cta" to="/timetable">
                時間割を開く
              </Link>
            </>
          ) : (
            <p>ログインすると履修中の授業が表示されます</p>
          )
        }
      />
      <Section
        title="最近活発な授業"
        section="active"
        cards={active}
        empty={<p>最近トークがある授業はまだありません</p>}
      />
      <Section
        title="人気の授業"
        section="popular"
        cards={popular}
        empty={<p>人気の授業はまだありません</p>}
      />
    </div>
  );
}
