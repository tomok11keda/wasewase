import { isAuthOrDiagRoute } from "../../lib/pushPrePermission.ts";
import type { NotificationItem } from "../notifications/api";
import type { ManagedOrganization } from "./managedOrganizations";

export const ORG_GRANT_QUERY_KEY = "org_grant";
export const ORG_GRANT_QUERY_VALUE = "1";
export const ORG_GRANT_PROMPT_STORAGE_PREFIX = "wase_org_grant_prompt:";
export const ORG_GRANT_PROMPT_TITLE = "団体アカウントが追加されました！";
export const ORG_GRANT_SWITCH_LABEL = "団体アカウントに切り替える";
export const ORG_GRANT_LATER_LABEL = "あとで";
export const ORG_GRANT_MISSING_GUIDANCE =
  "この団体の管理権限は現在ありません。";
export const ORG_GRANT_SWITCHER_GUIDANCE =
  "左上のプロフィールアイコンから団体アカウントに切り替えられます。";

export type OrgGrantCandidate = {
  id: number;
  slug: string;
};

export type OrgGrantPromptInput = {
  authenticated: boolean;
  onboardingRequired: boolean;
  pathname: string;
  organizationsLoading: boolean;
  organizations: Pick<ManagedOrganization, "slug" | "can_manage">[];
  activeOrganizationSlug: string | null;
  unseen: OrgGrantCandidate | null;
  handlingGrantLocation: boolean;
};

function storage(): Storage | null {
  try {
    const root =
      typeof window !== "undefined"
        ? window
        : (globalThis as { localStorage?: Storage });
    return root.localStorage ?? null;
  } catch {
    return null;
  }
}

export function orgGrantPromptStorageKey(userId: number): string {
  return `${ORG_GRANT_PROMPT_STORAGE_PREFIX}${userId}`;
}

function splitPathAndSearch(raw: string): { pathname: string; search: string } {
  let value = (raw || "").trim();
  const hashIdx = value.indexOf("#");
  if (hashIdx >= 0) value = value.slice(0, hashIdx);
  const qIdx = value.indexOf("?");
  let pathname = qIdx >= 0 ? value.slice(0, qIdx) : value;
  const search = qIdx >= 0 ? value.slice(qIdx) : "";
  if (pathname.startsWith("/app/")) pathname = pathname.slice(4) || "/";
  else if (pathname === "/app") pathname = "/";
  if (pathname.length > 1) pathname = pathname.replace(/\/+$/, "");
  return { pathname, search };
}

export function parseOrgGrantLocation(
  pathname: string,
  search: string
): { slug: string } | null {
  const params = new URLSearchParams(
    search.startsWith("?") ? search.slice(1) : search
  );
  if (params.get(ORG_GRANT_QUERY_KEY) !== ORG_GRANT_QUERY_VALUE) return null;
  const path = (pathname || "/").replace(/\/+$/, "") || "/";
  const match = path.match(/^\/(?:orgs|organizations)\/([^/]+)$/);
  if (!match) return null;
  try {
    const slug = decodeURIComponent(match[1] || "").trim();
    return slug ? { slug } : null;
  } catch {
    return null;
  }
}

export function orgGrantSlugFromNotification(
  item: Pick<NotificationItem, "spa_path" | "link">
): string | null {
  for (const raw of [item.spa_path, item.link]) {
    if (!raw) continue;
    const parts = splitPathAndSearch(raw);
    const parsed = parseOrgGrantLocation(parts.pathname, parts.search);
    if (parsed) return parsed.slug;
  }
  return null;
}

export function readSeenOrgGrantNotificationIds(userId: number): number[] {
  if (!Number.isInteger(userId) || userId <= 0) return [];
  const raw = storage()?.getItem(orgGrantPromptStorageKey(userId));
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (value): value is number =>
        typeof value === "number" && Number.isInteger(value) && value > 0
    );
  } catch {
    return [];
  }
}

export function markOrgGrantPromptSeen(
  userId: number,
  notificationId: number
): number[] {
  if (!Number.isInteger(userId) || userId <= 0) return [];
  if (!Number.isInteger(notificationId) || notificationId <= 0) {
    return readSeenOrgGrantNotificationIds(userId);
  }
  const next = [
    ...new Set([...readSeenOrgGrantNotificationIds(userId), notificationId]),
  ];
  try {
    storage()?.setItem(orgGrantPromptStorageKey(userId), JSON.stringify(next));
  } catch {
    /* ignore quota / private mode */
  }
  return next;
}

export function pickUnseenOrgGrantNotification(
  items: Pick<NotificationItem, "id" | "spa_path" | "link">[],
  seenIds: number[]
): OrgGrantCandidate | null {
  const seen = new Set(seenIds);
  for (const item of items) {
    if (!Number.isInteger(item.id) || item.id <= 0 || seen.has(item.id)) {
      continue;
    }
    const slug = orgGrantSlugFromNotification(item);
    if (slug) return { id: item.id, slug };
  }
  return null;
}

export function managedOrganizationForGrantSlug(
  organizations: Pick<ManagedOrganization, "slug" | "can_manage">[],
  slug: string
): Pick<ManagedOrganization, "slug" | "can_manage"> | null {
  const needle = slug.trim();
  if (!needle) return null;
  return (
    organizations.find(
      (item) => item.slug === needle && item.can_manage
    ) || null
  );
}

export function shouldShowOrganizationGrantPrompt(
  input: OrgGrantPromptInput
): boolean {
  if (!input.authenticated) return false;
  if (input.onboardingRequired) return false;
  if (isAuthOrDiagRoute(input.pathname)) return false;
  if (input.handlingGrantLocation) return false;
  if (input.organizationsLoading) return false;
  if (!input.unseen) return false;
  if (input.activeOrganizationSlug === input.unseen.slug) return false;
  return (
    managedOrganizationForGrantSlug(input.organizations, input.unseen.slug) !=
    null
  );
}

export function orgGrantGuidanceMessage(hasManagedOrganizations: boolean): string {
  return hasManagedOrganizations
    ? ORG_GRANT_SWITCHER_GUIDANCE
    : ORG_GRANT_MISSING_GUIDANCE;
}

export function stripOrgGrantSearch(search: string): string {
  const params = new URLSearchParams(
    search.startsWith("?") ? search.slice(1) : search
  );
  params.delete(ORG_GRANT_QUERY_KEY);
  const next = params.toString();
  return next ? `?${next}` : "";
}
