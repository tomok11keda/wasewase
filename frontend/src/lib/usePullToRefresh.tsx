import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import {
  PTR_ERROR_MS,
  PTR_MOBILE_MEDIA,
  canStartPtrGesture,
  clampPtrPull,
  isPtrArmed,
  shouldActivatePtrPull,
  shouldCancelPtrBeforeActivate,
  shouldPtrPreventDefault,
  type PtrStatus,
} from "./pullToRefreshPolicy";

export {
  PTR_ARM_PX,
  PTR_EDGE_GUARD_PX,
  PTR_ERROR_MS,
  PTR_MAX_PULL_PX,
  PTR_MOBILE_MAX_WIDTH_PX,
  PTR_MOBILE_MEDIA,
  PTR_THRESHOLD_PX,
  PTR_TOP_MAX_SCROLL_Y,
} from "./pullToRefreshPolicy";

export type PullToRefreshOptions = {
  enabled: boolean;
  onRefresh: () => void | Promise<void>;
};

type GestureSession = {
  startX: number;
  startY: number;
  activated: boolean;
};

function currentScrollY(): number {
  return window.scrollY || document.documentElement.scrollTop || 0;
}

function PtrIndicator({ status, pullPx }: { status: PtrStatus; pullPx: number }) {
  if (status === "idle" && pullPx <= 0) return null;
  if (typeof document === "undefined") return null;

  const label =
    status === "refreshing"
      ? "更新中..."
      : status === "error"
        ? "更新に失敗しました"
        : status === "armed"
          ? "離して更新"
          : "";

  return createPortal(
    <div
      className="ptr-indicator"
      data-ptr="true"
      data-state={status}
      style={{ ["--ptr-pull"]: `${pullPx}px` } as CSSProperties}
      aria-live="polite"
      aria-busy={status === "refreshing"}
    >
      <div className="ptr-indicator__nub">
        <span className="ptr-indicator__spinner" aria-hidden="true" />
        {label ? <span className="ptr-indicator__label">{label}</span> : null}
      </div>
    </div>,
    document.body
  );
}

/**
 * Shared SPA Pull-to-Refresh. Pages pass only `enabled` + `onRefresh`.
 * The indicator portals to document.body so keep-alive overflow cannot clip it.
 */
export function usePullToRefresh({
  enabled,
  onRefresh,
}: PullToRefreshOptions): { status: PtrStatus; pullPx: number } {
  const [status, setStatus] = useState<PtrStatus>("idle");
  const [pullPx, setPullPx] = useState(0);
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false;
    }
    return window.matchMedia(PTR_MOBILE_MEDIA).matches;
  });

  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;
  const statusRef = useRef(status);
  statusRef.current = status;
  const pullRef = useRef(pullPx);
  pullRef.current = pullPx;
  const sessionRef = useRef<GestureSession | null>(null);
  const errorTimerRef = useRef<number>(0);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  const mobileRef = useRef(isMobile);
  mobileRef.current = isMobile;

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(PTR_MOBILE_MEDIA);
    const sync = () => setIsMobile(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    return () => {
      if (errorTimerRef.current) window.clearTimeout(errorTimerRef.current);
    };
  }, []);

  useEffect(() => {
    const active = enabled && isMobile;
    if (!active) {
      sessionRef.current = null;
      if (errorTimerRef.current) {
        window.clearTimeout(errorTimerRef.current);
        errorTimerRef.current = 0;
      }
      setPullPx(0);
      if (statusRef.current !== "idle") {
        statusRef.current = "idle";
        setStatus("idle");
      }
      return;
    }

    let cancelled = false;

    const resetGesture = () => {
      sessionRef.current = null;
      setPullPx(0);
      if (statusRef.current !== "refreshing" && statusRef.current !== "error") {
        setStatus("idle");
      }
    };

    const finishCycle = () => {
      if (cancelled) return;
      sessionRef.current = null;
      pullRef.current = 0;
      statusRef.current = "idle";
      setPullPx(0);
      setStatus("idle");
    };

    const onStart = (event: TouchEvent) => {
      const touch = event.touches[0];
      if (!touch) return;
      if (
        !canStartPtrGesture({
          enabled: enabledRef.current,
          isMobile: mobileRef.current,
          refreshing:
            statusRef.current === "refreshing" || statusRef.current === "error",
          touchCount: event.touches.length,
          scrollY: currentScrollY(),
          clientX: touch.clientX,
        })
      ) {
        sessionRef.current = null;
        return;
      }
      sessionRef.current = {
        startX: touch.clientX,
        startY: touch.clientY,
        activated: false,
      };
    };

    const onMove = (event: TouchEvent) => {
      const session = sessionRef.current;
      if (!session) return;
      if (event.touches.length !== 1) {
        resetGesture();
        return;
      }
      const touch = event.touches[0];
      if (!touch) {
        resetGesture();
        return;
      }
      const dx = touch.clientX - session.startX;
      const dy = touch.clientY - session.startY;

      if (!session.activated) {
        if (shouldCancelPtrBeforeActivate(dx, dy)) {
          sessionRef.current = null;
          return;
        }
        if (!shouldActivatePtrPull(dx, dy)) {
          return;
        }
        session.activated = true;
      }

      if (shouldPtrPreventDefault(session.activated, dy)) {
        event.preventDefault();
      }

      const nextPull = clampPtrPull(dy);
      pullRef.current = nextPull;
      setPullPx(nextPull);
      setStatus(isPtrArmed(nextPull) ? "armed" : "pulling");
    };

    const runRefresh = () => {
      if (
        cancelled ||
        statusRef.current === "refreshing" ||
        statusRef.current === "error"
      ) {
        return;
      }
      setStatus("refreshing");
      statusRef.current = "refreshing";
      void Promise.resolve(onRefreshRef.current()).then(
        () => {
          finishCycle();
        },
        () => {
          if (cancelled) return;
          setStatus("error");
          statusRef.current = "error";
          if (errorTimerRef.current) window.clearTimeout(errorTimerRef.current);
          errorTimerRef.current = window.setTimeout(() => {
            finishCycle();
          }, PTR_ERROR_MS);
        }
      );
    };

    const onEnd = () => {
      const session = sessionRef.current;
      sessionRef.current = null;
      if (!session?.activated) {
        if (statusRef.current === "pulling" || statusRef.current === "armed") {
          setPullPx(0);
          setStatus("idle");
        }
        return;
      }
      if (
        isPtrArmed(pullRef.current) &&
        statusRef.current !== "refreshing" &&
        statusRef.current !== "error"
      ) {
        runRefresh();
        return;
      }
      setPullPx(0);
      setStatus("idle");
    };

    window.addEventListener("touchstart", onStart, { passive: true });
    window.addEventListener("touchmove", onMove, { passive: false });
    window.addEventListener("touchend", onEnd, { passive: true });
    window.addEventListener("touchcancel", onEnd, { passive: true });
    return () => {
      cancelled = true;
      sessionRef.current = null;
      window.removeEventListener("touchstart", onStart);
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("touchend", onEnd);
      window.removeEventListener("touchcancel", onEnd);
    };
  }, [enabled, isMobile]);

  return { status, pullPx };
}

/** Drop-in host: pages pass enabled + onRefresh only. */
export function PullToRefresh({ enabled, onRefresh }: PullToRefreshOptions) {
  const { status, pullPx } = usePullToRefresh({ enabled, onRefresh });
  return <PtrIndicator status={status} pullPx={pullPx} />;
}
