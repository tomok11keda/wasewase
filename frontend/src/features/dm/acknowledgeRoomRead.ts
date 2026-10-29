import { isSameUserScope } from "../../lib/userScopedResult.ts";
import type { InboxItem } from "./api.ts";
import { clearInboxRoomUnread } from "./inboxCache.ts";

export function nextDmUnreadTotal(
  currentTotal: number,
  roomUnread: number
): number {
  const total = Number.isFinite(currentTotal)
    ? Math.max(0, Math.trunc(currentTotal))
    : 0;
  const cleared = Number.isFinite(roomUnread)
    ? Math.max(0, Math.trunc(roomUnread))
    : 0;
  return Math.max(0, total - cleared);
}

export function unreadTotalAfterReadAttempt(args: {
  currentTotal: number;
  roomUnread: number;
  readSucceeded: boolean;
  serverTotal?: number;
}): number {
  if (typeof args.serverTotal === "number" && Number.isFinite(args.serverTotal)) {
    return Math.max(0, Math.trunc(args.serverTotal));
  }
  if (!args.readSucceeded) return nextDmUnreadTotal(args.currentTotal, 0);
  return nextDmUnreadTotal(args.currentTotal, args.roomUnread);
}

export function shouldCommitUnreadFetch(args: {
  fetchGen: number;
  currentGen: number;
  startedUserId: number | null | undefined;
  currentUserId: number | null | undefined;
}): boolean {
  if (args.fetchGen !== args.currentGen) return false;
  return isSameUserScope(args.startedUserId, args.currentUserId);
}

export function applyOpenedInboxRoomRead(args: {
  userId: number;
  kind: InboxItem["kind"];
  roomId: number;
  currentTotal: number;
}): { nextTotal: number; roomUnread: number } {
  const roomUnread = clearInboxRoomUnread(args.userId, args.kind, args.roomId);
  return {
    roomUnread,
    nextTotal: nextDmUnreadTotal(args.currentTotal, roomUnread),
  };
}
