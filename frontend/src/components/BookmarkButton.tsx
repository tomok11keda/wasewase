import { BookmarkIcon } from "./BookmarkIcon";

type Props = {
  bookmarked: boolean;
  disabled?: boolean;
  onClick: () => void;
};

/** タイムライン／フリマ共通の保存トグル（見た目・a11y を統一）。 */
export function BookmarkButton({ bookmarked, disabled, onClick }: Props) {
  return (
    <button
      type="button"
      className={`tweet-menu-btn tweet-menu-btn--icon${
        bookmarked ? " is-bookmarked" : ""
      }`}
      aria-pressed={bookmarked}
      aria-label={bookmarked ? "保存解除" : "保存"}
      title="保存"
      disabled={disabled}
      onClick={onClick}
    >
      <BookmarkIcon />
    </button>
  );
}
