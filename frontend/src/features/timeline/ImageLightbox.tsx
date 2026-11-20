import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type SyntheticEvent,
} from "react";
import { createPortal } from "react-dom";
import {
  backdropOpacityForOffset,
  isEdgeBackGestureStart,
  prefersReducedMotion,
  resolveSwipeAxis,
  scaleForOffset,
  shouldDismissSwipe,
  swipeDragOffsetY,
  SWIPE_CLICK_SUPPRESS_MS,
  type SwipeAxis,
} from "./imageLightboxGesture";

type Props = {
  src: string;
  alt?: string;
  open: boolean;
  onClose: () => void;
};

const BODY_OPEN_CLASS = "image-lightbox-open";

export function ImageLightbox({ src, alt = "", open, onClose }: Props) {
  const titleId = useId();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const closeBtnRef = useRef<HTMLButtonElement | null>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const closedRef = useRef(false);
  const suppressClickUntilRef = useRef(0);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    startTime: number;
    axis: SwipeAxis;
    offsetY: number;
    active: boolean;
  } | null>(null);
  const [dragY, setDragY] = useState(0);
  const [dragging, setDragging] = useState(false);

  const requestClose = useCallback(() => {
    if (closedRef.current) return;
    closedRef.current = true;
    onClose();
  }, [onClose]);

  useLayoutEffect(() => {
    if (!open) {
      closedRef.current = false;
      setDragY(0);
      setDragging(false);
      dragRef.current = null;
      return;
    }
    closedRef.current = false;
    const active = document.activeElement;
    restoreFocusRef.current =
      active instanceof HTMLElement ? active : null;
  }, [open]);

  useEffect(() => {
    if (!open) return;

    document.body.classList.add(BODY_OPEN_CLASS);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const focusTimer = window.setTimeout(() => {
      closeBtnRef.current?.focus({ preventScroll: true });
    }, 0);

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        requestClose();
        return;
      }
      if (event.key !== "Tab" || !rootRef.current) return;
      // Single primary control: keep focus inside the dialog.
      // Exclude tabindex=-1 controls (backdrop) from the trap cycle.
      const focusables = rootRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]):not([tabindex="-1"]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (focusables.length === 0) {
        event.preventDefault();
        closeBtnRef.current?.focus();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (event.shiftKey) {
        if (active === first || !rootRef.current.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last || !rootRef.current.contains(active)) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", onKeyDown, true);

    return () => {
      window.clearTimeout(focusTimer);
      window.removeEventListener("keydown", onKeyDown, true);
      document.body.classList.remove(BODY_OPEN_CLASS);
      document.body.style.overflow = prevOverflow;
      const restore = restoreFocusRef.current;
      restoreFocusRef.current = null;
      if (restore && document.contains(restore)) {
        try {
          restore.focus({ preventScroll: true });
        } catch {
          /* ignore */
        }
      }
    };
  }, [open, requestClose]);

  const endDrag = useCallback(
    (opts: { cancel: boolean }) => {
      const drag = dragRef.current;
      dragRef.current = null;
      if (!drag?.active) {
        setDragging(false);
        setDragY(0);
        return;
      }

      const elapsed = Math.max(1, performance.now() - drag.startTime);
      const dismiss =
        !opts.cancel &&
        shouldDismissSwipe({
          offsetY: drag.offsetY,
          elapsedMs: elapsed,
          axis: drag.axis,
        });

      // Any resolved pan (vertical or horizontal) should not synthesize a click-close.
      if (drag.axis !== "undecided") {
        suppressClickUntilRef.current = performance.now() + SWIPE_CLICK_SUPPRESS_MS;
      }

      setDragging(false);

      if (dismiss) {
        setDragY(drag.offsetY);
        requestClose();
        return;
      }

      setDragY(0);
    },
    [requestClose]
  );

  const onPointerDown = (event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0 && event.pointerType === "mouse") return;
    if (isEdgeBackGestureStart(event.clientX, window.innerWidth)) return;
    // Close button handles its own clicks.
    if (
      event.target instanceof Element &&
      event.target.closest(".image-lightbox__close")
    ) {
      return;
    }

    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startTime: performance.now(),
      axis: "undecided",
      offsetY: 0,
      active: true,
    };
    setDragging(true);
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      /* older WebViews may reject capture on some nodes */
    }
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag?.active || drag.pointerId !== event.pointerId) return;

    const axis = resolveSwipeAxis(
      drag.startX,
      drag.startY,
      event.clientX,
      event.clientY,
      drag.axis
    );
    drag.axis = axis;
    const offsetY = swipeDragOffsetY(drag.startY, event.clientY, axis);
    drag.offsetY = offsetY;
    if (axis === "vertical") {
      event.preventDefault();
      setDragY(offsetY);
    }
  };

  const onPointerUp = (event: ReactPointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    try {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    } catch {
      /* ignore */
    }
    endDrag({ cancel: false });
  };

  const onPointerCancel = (event: ReactPointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    endDrag({ cancel: true });
  };

  const onDismissClick = (event: SyntheticEvent) => {
    event.preventDefault();
    event.stopPropagation();
    if (performance.now() < suppressClickUntilRef.current) return;
    requestClose();
  };

  const onDialogKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      requestClose();
    }
  };

  if (!open) return null;

  const reduced = prefersReducedMotion();
  const opacity = backdropOpacityForOffset(dragY);
  const scale = scaleForOffset(dragY);
  const imgTransform =
    dragY > 0 ? `translate3d(0, ${dragY}px, 0) scale(${scale})` : undefined;

  return createPortal(
    <div
      ref={rootRef}
      className={`image-lightbox${dragging ? " is-dragging" : ""}`}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onKeyDown={onDialogKeyDown}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      style={{
        backgroundColor: `rgba(0, 0, 0, ${opacity})`,
      }}
    >
      <button
        type="button"
        className="image-lightbox__backdrop"
        aria-label="閉じる"
        tabIndex={-1}
        onClick={onDismissClick}
      />
      <button
        ref={closeBtnRef}
        type="button"
        className="image-lightbox__close"
        aria-label="閉じる"
        onClick={onDismissClick}
      >
        <span aria-hidden="true">×</span>
      </button>
      <div className="image-lightbox__stage">
        <h2 id={titleId} className="visually-hidden">
          画像
        </h2>
        <img
          className="image-lightbox__img"
          src={src}
          alt={alt}
          draggable={false}
          onClick={onDismissClick}
          style={{
            transform: imgTransform,
            transition:
              dragging || reduced
                ? "none"
                : "transform 160ms ease-out",
            touchAction: "none",
          }}
        />
      </div>
    </div>,
    document.body
  );
}
