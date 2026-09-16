import { getCsrfToken } from "../timeline/api";
import { userFacingMutationError } from "../../lib/rateLimit";

export type ShareTargetType = "timeline" | "flea";

export type ShareTarget = {
  type: ShareTargetType;
  id: number;
};

export type ShareAuthor = {
  id: number | null;
  username: string;
  display_name: string;
  avatar_url: string;
  initial: string;
};

export type ShareRecipient = {
  user_id: number;
  room_id: number;
  username: string;
  display_name: string;
  avatar_url: string;
  initial: string;
};

export type TimelineShareContent = {
  id: number;
  body_preview: string;
  image_url: string | null;
  author: ShareAuthor | null;
};

export type FleaShareContent = {
  id: number;
  name: string;
  price: number;
  image_url: string;
  seller: ShareAuthor | null;
};

export type ShareCardPayload = {
  type: ShareTargetType;
  id: number;
  available: boolean;
  content?: TimelineShareContent | FleaShareContent;
};

export async function fetchShareRecipients(signal?: AbortSignal): Promise<{
  recipients: ShareRecipient[];
  all_recipients: ShareRecipient[];
  has_more: boolean;
  total: number;
}> {
  const res = await fetch("/api/v1/dm/share/recipients/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error(data.error || "recipients_failed");
  }
  return {
    recipients: Array.isArray(data.recipients) ? data.recipients : [],
    all_recipients: Array.isArray(data.all_recipients)
      ? data.all_recipients
      : [],
    has_more: Boolean(data.has_more),
    total: Number(data.total || 0),
  };
}

export async function sendShareToRecipient(
  userId: number,
  target: ShareTarget
): Promise<void> {
  const res = await fetch("/api/v1/dm/share/send/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      user_id: userId,
      target_type: target.type,
      target_id: target.id,
    }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    throw new Error(
      userFacingMutationError(data.error || "send_failed", "送信に失敗しました")
    );
  }
}
