import {
  useCallback,
  useEffect,
  useRef,
  type MouseEvent,
  type PointerEvent,
} from "react";

const LONG_PRESS_MS = 480;
const MOVE_CANCEL_PX = 10;

type Options = {
  onLongPress: () => void;
  enabled?: boolean;
};

/**
 * Touch/pointer long-press with scroll-cancel. Avoids firing on short taps.
 */
export function useLongPress({ onLongPress, enabled = true }: Options) {
  const timerRef = useRef<number | null>(null);
  const startRef = useRef<{ x: number; y: number } | null>(null);
  const firedRef = useRef(false);

  const clear = useCallback(() => {
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    startRef.current = null;
  }, []);

  useEffect(() => () => clear(), [clear]);

  const onPointerDown = useCallback(
    (e: PointerEvent) => {
      if (!enabled) return;
      if (e.pointerType === "mouse" && e.button !== 0) return;
      firedRef.current = false;
      startRef.current = { x: e.clientX, y: e.clientY };
      timerRef.current = window.setTimeout(() => {
        firedRef.current = true;
        onLongPress();
      }, LONG_PRESS_MS);
    },
    [enabled, onLongPress]
  );

  const onPointerMove = useCallback(
    (e: PointerEvent) => {
      if (!startRef.current || timerRef.current == null) return;
      const dx = Math.abs(e.clientX - startRef.current.x);
      const dy = Math.abs(e.clientY - startRef.current.y);
      if (dx > MOVE_CANCEL_PX || dy > MOVE_CANCEL_PX) {
        clear();
      }
    },
    [clear]
  );

  const onPointerUp = useCallback(() => {
    clear();
  }, [clear]);

  const onPointerCancel = useCallback(() => {
    clear();
  }, [clear]);

  const onContextMenu = useCallback(
    (e: MouseEvent) => {
      if (!enabled) return;
      e.preventDefault();
      onLongPress();
    },
    [enabled, onLongPress]
  );

  return {
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onPointerCancel,
    onPointerLeave: onPointerUp,
    onContextMenu,
    didFire: () => firedRef.current,
  };
}
