import type { NotificationItem } from "./api";

export type NotificationsCacheEntry = {
  userId: number;
  items: NotificationItem[];
  pendingFollowRequests: number;
  fetchedAt: number;
};

export const NOTIFICATIONS_CACHE_FRESH_MS = 20_000;

const store = new Map<number, NotificationsCacheEntry>();

function isValidUserId(userId: number): boolean {
  return Number.isFinite(userId) && userId > 0;
}

export function readNotificationsCache(
  userId: number
): NotificationsCacheEntry | null {
  if (!isValidUserId(userId)) return null;
  const hit = store.get(userId);
  if (!hit || hit.userId !== userId) return null;
  return hit;
}

export function isNotificationsCacheFresh(
  entry: NotificationsCacheEntry,
  now = Date.now()
): boolean {
  return now - entry.fetchedAt < NOTIFICATIONS_CACHE_FRESH_MS;
}

export function writeNotificationsCache(entry: NotificationsCacheEntry): void {
  if (!isValidUserId(entry.userId)) return;
  store.set(entry.userId, entry);
}

export function writeNotificationsCacheForUser(
  currentUserId: number | null | undefined,
  entry: NotificationsCacheEntry
): boolean {
  if (currentUserId !== entry.userId) return false;
  if (!isValidUserId(entry.userId)) return false;
  writeNotificationsCache(entry);
  return true;
}

export function clearNotificationsCache(userId?: number): void {
  if (userId == null) {
    store.clear();
    return;
  }
  store.delete(userId);
}
