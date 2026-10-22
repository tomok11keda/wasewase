/** Org edit is the only actor-specific management screen today. */
export function organizationEditSlug(pathname: string): string | null {
  const normalized = pathname.replace(/\/+$/, "") || "/";
  const match = normalized.match(/^\/orgs\/([^/]+)\/edit$/);
  return match ? match[1] : null;
}

export function shouldLeaveOrganizationEdit(
  pathname: string,
  nextOrganizationSlug: string | null
): boolean {
  const current = organizationEditSlug(pathname);
  if (!current) return false;
  return current !== nextOrganizationSlug;
}

export function accountSwitchMessage(name: string): string {
  return `${name}に切り替えました`;
}
