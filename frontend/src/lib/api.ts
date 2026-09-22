export type MeResponse = {
  authenticated: boolean;
  is_browse_mode: boolean;
  react_spa_enabled: boolean;
  is_staff?: boolean;
  is_superuser?: boolean;
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
  onboarding_required?: boolean;
  onboarding_step?: string | null;
  onboarding_completed?: boolean;
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

export type InternalPushDiagResponse = {
  ok: true;
  authenticated: boolean;
  user_id: number;
  is_staff: boolean;
  is_superuser: boolean;
  device_push_token_count: number;
};

/** Staff/superuser only. 404 → null. Never reads or returns device tokens. */
export async function fetchInternalPushDiag(): Promise<InternalPushDiagResponse | null> {
  const res = await fetch("/api/v1/internal/push-diag/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`push_diag_failed_${res.status}`);
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
