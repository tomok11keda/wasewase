export type MeResponse = {
  authenticated: boolean;
  is_browse_mode: boolean;
  react_spa_enabled: boolean;
  user: null | {
    id: number;
    email: string;
    username: string;
    display_name: string;
    avatar_url: string;
    initial: string;
    department?: string;
  };
  unread_notifications: number;
  dm_unread_total: number;
};

export async function fetchMe(): Promise<MeResponse> {
  const res = await fetch("/api/v1/me/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`me_failed_${res.status}`);
  }
  return res.json();
}

export async function fetchNotificationUnread(): Promise<number> {
  const res = await fetch("/api/notifications/unread-count/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) return 0;
  const data = await res.json();
  return Number(data.unread_count || 0);
}

export async function fetchDmUnreadTotal(): Promise<number> {
  const res = await fetch("/api/dm/unread-summary/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) return 0;
  const data = await res.json();
  return Number(data.total_unread || 0);
}
