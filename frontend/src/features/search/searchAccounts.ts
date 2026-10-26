export const SEARCH_USERS_TAB_LABEL = "アカウント";

export const SEARCH_RESULT_KINDS = [
  "post",
  "thread",
  "user",
  "product",
  "offering",
  "organization",
] as const;

export type HandledSearchResultKind = (typeof SEARCH_RESULT_KINDS)[number];

export function isHandledSearchResultKind(
  kind: string | null | undefined
): kind is HandledSearchResultKind {
  return SEARCH_RESULT_KINDS.includes(kind as HandledSearchResultKind);
}

export function organizationSearchHref(slug: string): string {
  const trimmed = slug.trim();
  return trimmed ? `/orgs/${trimmed}` : "";
}
