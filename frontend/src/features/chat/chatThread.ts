/** Client-only thread layout. Does not invent read receipts or timestamps. */

export type ChatStamp = {
  id: number;
  sender_id?: number | null;
  sender_name?: string;
  is_mine: boolean;
  created_at: string;
  is_system?: boolean;
};

export type ChatCluster = "solo" | "start" | "middle" | "end";

export type ChatThreadLayout = {
  showAvatar: boolean;
  showSender: boolean;
  showTime: boolean;
  cluster: ChatCluster;
};

export type ChatThreadEntry<T> =
  | { kind: "day"; key: string; label: string }
  | { kind: "message"; message: T; layout: ChatThreadLayout };

export type ChatThreadOptions = {
  /** 1:1 DM: hide per-bubble avatars. Groups/course/recruiting: show. */
  showPeerAvatar?: boolean;
  showPeerName?: boolean;
};

const DAY_TIME = /^(\d{1,2})\/(\d{1,2})\s+(\d{1,2}:\d{2})$/;

export function chatDayKey(createdAt: string): string {
  const raw = (createdAt || "").trim();
  const match = raw.match(DAY_TIME);
  if (match) {
    return `${match[1].padStart(2, "0")}/${match[2].padStart(2, "0")}`;
  }
  const space = raw.indexOf(" ");
  if (space > 0) return raw.slice(0, space);
  return raw || "unknown";
}

export function chatDayLabel(createdAt: string): string {
  const key = chatDayKey(createdAt);
  const match = key.match(/^(\d{1,2})\/(\d{1,2})$/);
  if (match) return `${Number(match[1])}月${Number(match[2])}日`;
  return key;
}

export function chatTimeLabel(createdAt: string): string {
  const raw = (createdAt || "").trim();
  const match = raw.match(DAY_TIME);
  if (match) return match[3];
  const space = raw.lastIndexOf(" ");
  if (space >= 0) {
    const tail = raw.slice(space + 1);
    if (/^\d{1,2}:\d{2}$/.test(tail)) return tail;
  }
  return raw;
}

function senderKey(message: ChatStamp): string {
  if (message.is_system) return `sys:${message.id}`;
  if (message.is_mine) return "mine";
  if (message.sender_id != null) return `u:${message.sender_id}`;
  return `n:${message.sender_name || ""}`;
}

function sameCluster(prev: ChatStamp, next: ChatStamp): boolean {
  if (prev.is_system || next.is_system) return false;
  if (chatDayKey(prev.created_at) !== chatDayKey(next.created_at)) return false;
  return senderKey(prev) === senderKey(next);
}

function clusterFor(isFirst: boolean, isLast: boolean): ChatCluster {
  if (isFirst && isLast) return "solo";
  if (isFirst) return "start";
  if (isLast) return "end";
  return "middle";
}

export function buildChatThread<T extends ChatStamp>(
  messages: T[],
  options: ChatThreadOptions = {}
): ChatThreadEntry<T>[] {
  const showPeerAvatar = options.showPeerAvatar !== false;
  const showPeerName = options.showPeerName !== false;
  const out: ChatThreadEntry<T>[] = [];
  let lastDay = "";

  for (let i = 0; i < messages.length; i += 1) {
    const message = messages[i];
    const day = chatDayKey(message.created_at);
    if (day !== lastDay) {
      lastDay = day;
      out.push({
        kind: "day",
        key: `day-${day}-${message.id}`,
        label: chatDayLabel(message.created_at),
      });
    }

    const prev = i > 0 ? messages[i - 1] : null;
    const next = i < messages.length - 1 ? messages[i + 1] : null;
    const clusteredWithPrev = prev ? sameCluster(prev, message) : false;
    const clusteredWithNext = next ? sameCluster(message, next) : false;
    const cluster = clusterFor(!clusteredWithPrev, !clusteredWithNext);
    const peer = !message.is_mine && !message.is_system;

    out.push({
      kind: "message",
      message,
      layout: {
        showAvatar: peer && showPeerAvatar && !clusteredWithPrev,
        showSender: peer && showPeerName && !clusteredWithPrev,
        showTime: !message.is_system && (cluster === "solo" || cluster === "end"),
        cluster,
      },
    });
  }

  return out;
}
