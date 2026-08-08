import { useEffect, useRef } from "react";

/**
 * Stable interval poller with AbortController.
 * - Clears interval on unmount / deps change
 * - Aborts in-flight fetch when leaving
 * - Skips ticks while document.hidden
 * - Uses callback ref so interval is NOT recreated when callback identity changes
 */
export function useChatPoll(
  enabled: boolean,
  intervalMs: number,
  tick: (signal: AbortSignal) => Promise<void>
): void {
  const tickRef = useRef(tick);
  tickRef.current = tick;

  useEffect(() => {
    if (!enabled) return;

    const controller = new AbortController();
    let cancelled = false;
    let inFlight = false;

    const run = async () => {
      if (cancelled || document.hidden || inFlight) return;
      inFlight = true;
      try {
        await tickRef.current(controller.signal);
      } catch (err) {
        if ((err as Error)?.name === "AbortError") return;
        /* swallow poll errors */
      } finally {
        inFlight = false;
      }
    };

    const id = window.setInterval(() => {
      void run();
    }, intervalMs);

    // Track for leak diagnostics in verify script
    const w = window as Window & { __WASE_ACTIVE_POLLS__?: number };
    w.__WASE_ACTIVE_POLLS__ = (w.__WASE_ACTIVE_POLLS__ || 0) + 1;

    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(id);
      w.__WASE_ACTIVE_POLLS__ = Math.max(0, (w.__WASE_ACTIVE_POLLS__ || 1) - 1);
    };
  }, [enabled, intervalMs]);
}

export const DM_POLL_MS = 15000;
export const TRADE_POLL_MS = 4000;
