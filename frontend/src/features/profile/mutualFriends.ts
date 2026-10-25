import type { FollowListUser } from "./followLists.ts";

export type MutualFriendsPreview = {
  count: number;
  users: FollowListUser[];
};

function parseFollowListUser(raw: unknown): FollowListUser | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const id = Number(row.id);
  if (!Number.isFinite(id) || id <= 0) return null;
  return {
    id,
    username: typeof row.username === "string" ? row.username : "",
    display_name:
      typeof row.display_name === "string" ? row.display_name : "",
    avatar_url: typeof row.avatar_url === "string" ? row.avatar_url : "",
    initial: typeof row.initial === "string" ? row.initial : "",
    is_operator_verified:
      typeof row.is_operator_verified === "boolean"
        ? row.is_operator_verified
        : null,
  };
}

/**
 * Server-authored preview only. Never invents people, counts, or avatars.
 * Missing / empty / unreadable payloads become null so the UI stays hidden.
 */
export function parseMutualFriendsPreview(
  raw: unknown
): MutualFriendsPreview | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const count = Number(row.count);
  if (!Number.isFinite(count) || count < 1) return null;
  const users = Array.isArray(row.users)
    ? row.users
        .map(parseFollowListUser)
        .filter((user): user is FollowListUser => user != null)
        .slice(0, 3)
    : [];
  return { count, users };
}

function displayName(user: FollowListUser): string {
  return (user.display_name || user.username || "").trim();
}

export function formatMutualFriendsLabel(
  preview: MutualFriendsPreview
): string {
  const names = preview.users
    .map(displayName)
    .filter(Boolean)
    .slice(0, 2);
  const extra = preview.count - names.length;
  if (names.length === 0) {
    return `${preview.count}人がフォロー中`;
  }
  if (extra <= 0) {
    if (names.length === 1) return `${names[0]}さんがフォロー中`;
    return `${names[0]}さん、${names[1]}さんがフォロー中`;
  }
  return `${names[0]}さん、${names[1]}さん、ほか${extra}人がフォロー中`;
}
