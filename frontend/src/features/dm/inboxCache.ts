import type { InboxItem } from "./api";

export type InboxCacheEntry = {
  userId: number;
  tab: string;
  items: InboxItem[];
  counts: Record<string, number>;
  requestCount: number;
  fetchedAt: number;
};

/** Show immediately and skip a refetch while this fresh. */
export const INBOX_CACHE_FRESH_MS = 20_000;

const store = new Map<string, InboxCacheEntry>();
const inflight = new Map<string, Promise<InboxCacheEntry>>();

function cacheKey(userId: number, tab: string): string {
  return `${userId}:${tab || "all"}`;
}

function isValidUserId(userId: number): boolean {
  return Number.isFinite(userId) && userId > 0;
}

export function readInboxCache(
  userId: number,
  tab: string
): InboxCacheEntry | null {
  if (!isValidUserId(userId)) return null;
  const hit = store.get(cacheKey(userId, tab));
  if (!hit || hit.userId !== userId) return null;
  return hit;
}

const INBOX_LOOKUP_TABS = ["all", "dm", "course", "trade"] as const;

/** Find a row the current user already saw in the inbox. Never crosses users. */
export function findInboxItemForUser(
  userId: number | null | undefined,
  match: (item: InboxItem) => boolean
): InboxItem | null {
  if (userId == null || !isValidUserId(userId)) return null;
  for (const tab of INBOX_LOOKUP_TABS) {
    const entry = readInboxCache(userId, tab);
    if (!entry || entry.userId !== userId) continue;
    const item = entry.items.find(match);
    if (item) return item;
  }
  return null;
}

export function isInboxCacheFresh(entry: InboxCacheEntry, now = Date.now()): boolean {
  return now - entry.fetchedAt < INBOX_CACHE_FRESH_MS;
}

export function writeInboxCache(entry: InboxCacheEntry): void {
  if (!isValidUserId(entry.userId)) return;
  store.set(cacheKey(entry.userId, entry.tab), entry);
}

export function clearInboxCache(userId?: number): void {
  if (userId == null) {
    store.clear();
    inflight.clear();
    return;
  }
  for (const key of [...store.keys()]) {
    if (key.startsWith(`${userId}:`)) store.delete(key);
  }
  for (const key of [...inflight.keys()]) {
    if (key.startsWith(`${userId}:`)) inflight.delete(key);
  }
}

export async function loadDmInbox(
  userId: number,
  tab = "all",
  options: { force?: boolean } = {}
): Promise<InboxCacheEntry> {
  if (!isValidUserId(userId)) {
    throw new Error("inbox_unauthenticated");
  }
  if (!options.force) {
    const hit = readInboxCache(userId, tab);
    if (hit && isInboxCacheFresh(hit)) return hit;
  }
  const key = cacheKey(userId, tab);
  const pending = inflight.get(key);
  if (pending) return pending;
  const request = import("./api").then(({ fetchDmInbox }) => fetchDmInbox(tab))
    .then((data) => {
      const entry: InboxCacheEntry = {
        userId,
        tab,
        items: data.conversations || [],
        counts: data.tab_counts || {},
        requestCount: Number(data.message_request_count || 0),
        fetchedAt: Date.now(),
      };
      writeInboxCache(entry);
      return entry;
    })
    .finally(() => {
      inflight.delete(key);
    });
  inflight.set(key, request);
  return request;
}

export async function prefetchDmInbox(
  userId: number,
  tab = "all"
): Promise<void> {
  try {
    await loadDmInbox(userId, tab);
  } catch {
    /* prefetch is best-effort */
  }
}
