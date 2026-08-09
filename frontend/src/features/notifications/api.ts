import { getCsrfToken } from "../timeline/api";

export type NotificationItem = {
  id: number;
  message: string;
  link: string;
  spa_path: string;
  is_read: boolean;
  created_at: string;
};

export async function fetchNotifications(markRead = true): Promise<{
  notifications: NotificationItem[];
  unread_count: number;
  marked_count: number;
  pending_follow_request_count: number;
}> {
  const qs = markRead ? "" : "?mark_read=0";
  const res = await fetch(`/api/v1/notifications/${qs}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "notifications_failed");
  return {
    notifications: data.notifications || [],
    unread_count: Number(data.unread_count || 0),
    marked_count: Number(data.marked_count || 0),
    pending_follow_request_count: Number(
      data.pending_follow_request_count || 0
    ),
  };
}

export async function markAllNotificationsRead(): Promise<number> {
  const res = await fetch("/api/v1/notifications/mark-read/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      Accept: "application/json",
    },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "mark_failed");
  return Number(data.marked_count || 0);
}
