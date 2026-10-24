import type { ProfilePayload } from "./api";

export const OWN_PROFILE_CACHE_FRESH_MS = 20_000;

type OwnProfileCacheEntry = {
  viewerId: number;
  profile: ProfilePayload;
  fetchedAt: number;
};

let store: OwnProfileCacheEntry | null = null;

function isValidUserId(userId: number): boolean {
  return Number.isFinite(userId) && userId > 0;
}

export function readOwnProfileCache(
  viewerId: number
): OwnProfileCacheEntry | null {
  if (!isValidUserId(viewerId)) return null;
  if (!store || store.viewerId !== viewerId) return null;
  if (store.profile.user.id !== viewerId || !store.profile.is_own) return null;
  return store;
}

export function isOwnProfileCacheFresh(
  entry: OwnProfileCacheEntry,
  now = Date.now()
): boolean {
  return now - entry.fetchedAt < OWN_PROFILE_CACHE_FRESH_MS;
}

export function writeOwnProfileCache(
  viewerId: number,
  profile: ProfilePayload
): void {
  if (!isValidUserId(viewerId)) return;
  if (!profile.is_own || profile.user.id !== viewerId) return;
  store = { viewerId, profile, fetchedAt: Date.now() };
}

/** Call only after a successful local mutation of the viewer's own profile. */
export function invalidateOwnProfileCacheAfterEdit(viewerId: number): void {
  if (!isValidUserId(viewerId)) return;
  clearOwnProfileCache(viewerId);
}

export function clearOwnProfileCache(viewerId?: number): void {
  if (viewerId == null || store?.viewerId === viewerId) {
    store = null;
  }
}
