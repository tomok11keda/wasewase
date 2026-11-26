export const SEARCH_USERS_TAB_LABEL = "アカウント";

/** Find-hub gate → existing アカウント search tab (users + orgs). */
export const ACCOUNTS_DISCOVERY_HREF = "/search?tab=users";

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
