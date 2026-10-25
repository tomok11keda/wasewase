export type DetailContentPhase =
  | "browse"
  | "skeleton"
  | "preview"
  | "ready"
  | "error";

export type DetailContentPhaseInput = {
  browsePreview: boolean;
  loading: boolean;
  error: string | null;
  hasItem: boolean;
  hydrated: boolean;
};

/**
 * Detail first paint: a matching location.state snapshot is "preview".
 * No snapshot waits on a skeleton. 403/404 must clear the item before this
 * runs so they surface as error, not a stale preview.
 */
export function detailContentPhase(
  input: DetailContentPhaseInput
): DetailContentPhase {
  if (input.browsePreview) return "browse";
  if (input.hasItem) return input.hydrated ? "ready" : "preview";
  if (input.error && !input.loading) return "error";
  if (input.loading) return "skeleton";
  return "error";
}

/** True only when the in-memory item belongs to the current route id. */
export function detailItemMatches(
  item: { id: number } | null | undefined,
  itemId: number
): boolean {
  return item != null && item.id === itemId;
}

/** Shown while a public snapshot is kept after a network failure. */
export const DETAIL_NETWORK_ERROR = "network";

/** Network failures may keep a public snapshot; 403/404 must not. */
export function isTransientDetailError(err: unknown): boolean {
  return err instanceof TypeError;
}

/**
 * Keep a matching list snapshot only for transport failures.
 * 403/404 still discard so unpublished rows cannot linger.
 */
export function shouldKeepDetailPreview(
  hadPreview: boolean,
  err: unknown
): boolean {
  return hadPreview && isTransientDetailError(err);
}

export function isUnavailableDetailError(err: unknown): boolean {
  if (isTransientDetailError(err)) return false;
  const message = err instanceof Error ? err.message : String(err);
  return /not_found|forbidden|unauthorized|表示できません|http_403|http_404|detail_failed/i.test(
    message
  );
}
