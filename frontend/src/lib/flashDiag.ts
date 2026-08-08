type FlashDiagApi = {
  isEnabled: () => boolean;
  refreshEnabled: () => boolean;
  beginTrace: (meta?: Record<string, unknown>) => string | null;
  endTrace: (meta?: Record<string, unknown>) => unknown;
  mark: (type: string, payload?: Record<string, unknown> | null) => unknown;
  snapshotNative: (reason?: string) => Promise<unknown>;
  exportTraces: () => unknown;
  clear: () => void;
  getActiveTraceId: () => string | null;
};

function api(): FlashDiagApi | null {
  return (
    (window as Window & { WaseFlashDiag?: FlashDiagApi }).WaseFlashDiag || null
  );
}

export function flashDiagEnabled(): boolean {
  try {
    return Boolean(api()?.isEnabled?.());
  } catch {
    return false;
  }
}

export function flashDiagBegin(meta?: Record<string, unknown>): string | null {
  try {
    return api()?.beginTrace?.(meta) ?? null;
  } catch {
    return null;
  }
}

export function flashDiagEnd(meta?: Record<string, unknown>): void {
  try {
    api()?.endTrace?.(meta);
  } catch {
    /* ignore */
  }
}

export function flashDiagMark(
  type: string,
  payload?: Record<string, unknown> | null
): void {
  try {
    api()?.mark?.(type, payload ?? null);
  } catch {
    /* ignore */
  }
}

export function flashDiagSnapshot(reason?: string): void {
  try {
    void api()?.snapshotNative?.(reason);
  } catch {
    /* ignore */
  }
}
