import {
  findInboxItemForUser,
} from "../dm/inboxCache.ts";
import type { InboxItem } from "../dm/api.ts";

export type ChatHeaderPreview = {
  title: string;
  subtitle?: string;
  avatarUrl?: string;
  avatarInitial?: string;
  avatarShape?: "circle" | "rounded";
};

/**
 * Header-only fields from the current user's inbox row.
 * Never copies latest_body — message text stays on the room API.
 */
export function headerPreviewFromInboxItem(
  item: InboxItem
): ChatHeaderPreview {
  if (item.kind === "dm" && item.is_blocked) {
    return { title: "不明なユーザー", avatarInitial: "?" };
  }
  if (item.kind === "trade") {
    return {
      title: item.display_name,
      subtitle: [item.status_label, item.partner?.display_name]
        .filter(Boolean)
        .join(" · ") || undefined,
      avatarUrl: item.thumbnail_url || undefined,
      avatarInitial: "📦",
      avatarShape: "rounded",
    };
  }
  if (item.kind === "course") {
    return {
      title: item.display_name,
      subtitle: item.subtitle || undefined,
      avatarInitial: (item.display_name || "授").slice(0, 1),
    };
  }
  if (item.kind === "recruiting" || item.kind === "recruiting_invite") {
    return {
      title: item.display_name,
      subtitle: item.organization_name || item.subtitle || "新歓チャット",
      avatarUrl:
        item.organization_avatar_url || item.thumbnail_url || undefined,
      avatarInitial: (item.display_name || "新").slice(0, 1),
      avatarShape: "rounded",
    };
  }
  if (item.kind === "group" || item.kind === "group_invite") {
    return {
      title: item.display_name,
      subtitle: item.subtitle || undefined,
      avatarInitial: (item.display_name || "G").slice(0, 1),
    };
  }
  return {
    title: item.display_name || "DM",
    subtitle: item.is_blocked ? undefined : item.subtitle || undefined,
    avatarUrl: item.thumbnail_url || item.partner?.avatar_url || undefined,
    avatarInitial: (
      item.partner?.initial ||
      item.display_name ||
      "?"
    ).slice(0, 1),
  };
}

export function readDmHeaderPreview(
  userId: number | null | undefined,
  roomId: number
): ChatHeaderPreview | null {
  const item = findInboxItemForUser(
    userId,
    (row) => row.kind === "dm" && row.room_id === roomId
  );
  return item ? headerPreviewFromInboxItem(item) : null;
}

export function readGroupHeaderPreview(
  userId: number | null | undefined,
  roomId: number
): ChatHeaderPreview | null {
  const item = findInboxItemForUser(
    userId,
    (row) =>
      (row.kind === "group" || row.kind === "group_invite") &&
      row.room_id === roomId
  );
  return item ? headerPreviewFromInboxItem(item) : null;
}

export function readCourseHeaderPreview(
  userId: number | null | undefined,
  offeringId: number
): ChatHeaderPreview | null {
  const item = findInboxItemForUser(
    userId,
    (row) => row.kind === "course" && row.offering_id === offeringId
  );
  return item ? headerPreviewFromInboxItem(item) : null;
}

export function readTradeHeaderPreview(
  userId: number | null | undefined,
  roomId: number
): ChatHeaderPreview | null {
  const item = findInboxItemForUser(
    userId,
    (row) => row.kind === "trade" && row.room_id === roomId
  );
  return item ? headerPreviewFromInboxItem(item) : null;
}

export function readRecruitingHeaderPreview(
  userId: number | null | undefined,
  slug: string
): ChatHeaderPreview | null {
  const item = findInboxItemForUser(
    userId,
    (row) =>
      (row.kind === "recruiting" || row.kind === "recruiting_invite") &&
      row.organization_slug === slug
  );
  return item ? headerPreviewFromInboxItem(item) : null;
}
