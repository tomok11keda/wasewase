import { type ReactNode } from "react";
import { Link } from "react-router-dom";

type Props = {
  title: string;
  children: ReactNode;
  /** Items currently rendered by parent (already sliced). */
  visibleCount: number;
  totalCount: number;
  expanded: boolean;
  onExpand: () => void;
  /** Extra destination after the list is fully expanded (optional). */
  moreTo?: string;
  moreLabel?: string;
};

/**
 * Discovery section with local "もっと見る" expand, then optional deep-link.
 */
export function DiscoverSection({
  title,
  children,
  visibleCount,
  totalCount,
  expanded,
  onExpand,
  moreTo,
  moreLabel = "もっと見る",
}: Props) {
  const canExpand = !expanded && visibleCount < totalCount;
  const showDeepLink = expanded && Boolean(moreTo);

  return (
    <section className="search-discover__section">
      <h2 className="search-discover__title">{title}</h2>
      {children}
      {canExpand ? (
        <button
          type="button"
          className="search-discover__more"
          onClick={onExpand}
        >
          もっと見る
        </button>
      ) : null}
      {showDeepLink && moreTo ? (
        <Link className="search-discover__more is-link" to={moreTo}>
          {moreLabel}
        </Link>
      ) : null}
    </section>
  );
}
