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
let writeGeneration = 0;

function bumpWriteGeneration(): void {
  writeGeneration += 1;
}

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

export function chooseInboxCacheEntry(args: {
  startedGeneration: number;
  currentGeneration: number;
  patched: InboxCacheEntry | null;
  fetched: InboxCacheEntry;
}): InboxCacheEntry {
  if (args.startedGeneration !== args.currentGeneration && args.patched) {
    return args.patched;
  }
  return args.fetched;
}

function itemMatchesRoom(
  item: InboxItem,
  kind: InboxItem["kind"],
  roomId: number
): boolean {
  return item.kind === kind && item.room_id === roomId;
}

/**
 * Zero this user's unread for one inbox room across cached tabs.
 * Returns the unread count that was cleared (0 if already read / missing).
 */
export function clearInboxRoomUnread(
  userId: number,
  kind: InboxItem["kind"],
  roomId: number
): number {
  if (!isValidUserId(userId) || !Number.isFinite(roomId) || roomId <= 0) {
    return 0;
  }
  let captured = 0;
  for (const [key, entry] of store) {
    if (entry.userId !== userId) continue;
    let entryChanged = false;
    const items = entry.items.map((item) => {
      if (!itemMatchesRoom(item, kind, roomId)) return item;
      const unread = Math.max(0, Math.trunc(Number(item.unread_count) || 0));
      captured = Math.max(captured, unread);
      if (unread === 0) return item;
      entryChanged = true;
      return { ...item, unread_count: 0 };
    });
    if (entryChanged) {
      store.set(key, { ...entry, items });
    }
  }
  bumpWriteGeneration();
  return captured;
}

export function clearInboxCache(userId?: number): void {
  bumpWriteGeneration();
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
  const startedGeneration = writeGeneration;
  const request = import("./api").then(({ fetchDmInbox }) => fetchDmInbox(tab))
    .then((data) => {
      const fetched: InboxCacheEntry = {
        userId,
        tab,
        items: data.conversations || [],
        counts: data.tab_counts || {},
        requestCount: Number(data.message_request_count || 0),
        fetchedAt: Date.now(),
      };
      const chosen = chooseInboxCacheEntry({
        startedGeneration,
        currentGeneration: writeGeneration,
        patched: readInboxCache(userId, tab),
        fetched,
      });
      if (chosen === fetched) writeInboxCache(fetched);
      return chosen;
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
