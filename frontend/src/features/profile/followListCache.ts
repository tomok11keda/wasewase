import type { FollowListUser } from "./followLists";

export type FollowListCacheEntry = {
  users: FollowListUser[];
  count: number;
  forbidden: boolean;
  error: string | null;
};

const memory = new Map<string, FollowListCacheEntry>();

export function readFollowListCache(
  key: string
): FollowListCacheEntry | null {
  return memory.get(key) ?? null;
}

export function writeFollowListCache(
  key: string,
  entry: FollowListCacheEntry
): void {
  memory.set(key, entry);
}

export function clearFollowListCache(): void {
  memory.clear();
}
