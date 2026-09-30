import { BookmarkIcon } from "./BookmarkIcon";
import { useRef, useState } from "react";
import { MOTION_FAST_MS } from "../lib/motion";

type Props = {
  bookmarked: boolean;
  disabled?: boolean;
  onClick: () => void;
  className?: string;
};

/** タイムライン／フリマ共通の保存トグル（見た目・a11y を統一）。 */
export function BookmarkButton({
  bookmarked,
  disabled,
  onClick,
  className,
}: Props) {
  const [popping, setPopping] = useState(false);
  const popTimerRef = useRef(0);

  return (
    <button
      type="button"
      className={`tweet-menu-btn tweet-menu-btn--icon${
        bookmarked ? " is-bookmarked" : ""
      }${popping ? " is-popping" : ""}${className ? ` ${className}` : ""}`}
      aria-pressed={bookmarked}
      aria-label={bookmarked ? "保存解除" : "保存"}
      title="保存"
      disabled={disabled}
      onClick={() => {
        if (!bookmarked) {
          setPopping(true);
          window.clearTimeout(popTimerRef.current);
          popTimerRef.current = window.setTimeout(() => {
            setPopping(false);
          }, MOTION_FAST_MS + 40);
        }
        onClick();
      }}
    >
      <BookmarkIcon />
    </button>
  );
}
