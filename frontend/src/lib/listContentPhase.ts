export type ListContentPhase =
  | "browse"
  | "skeleton"
  | "error"
  | "empty"
  | "ready";

export type ListContentPhaseInput = {
  browsePreview: boolean;
  loading: boolean;
  error: string | null;
  itemCount: number;
  /** False when in-memory rows belong to a previous query/filter/user. */
  matchesCurrentQuery?: boolean;
};

export function listQueryKey(
  parts: Array<string | number | boolean | null | undefined>
): string {
  return parts.map((part) => String(part ?? "")).join("\u0001");
}

/**
 * Keep already-loaded rows on the same query. Skeleton when the query changed
 * or the first response has not arrived. An applied empty result stays empty
 * during same-query refetch. Browse preview never uses a logged-in placeholder.
 */
export function listContentPhase(
  input: ListContentPhaseInput
): ListContentPhase {
  if (input.browsePreview) return "browse";
  const matches = input.matchesCurrentQuery !== false;
  if (matches && input.itemCount > 0) return "ready";
  if (matches) {
    if (input.error && !input.loading) return "error";
    return "empty";
  }
  if (input.error && !input.loading) return "error";
  return "skeleton";
}
